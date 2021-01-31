"""
Download Data
https://www.kaggle.com/c/nlp-getting-started/data (tweet)
https://www.kaggle.com/team-ai/spam-text-message-classification (spam)
Install pandas (data loading)
"""
import time

from sentence_transformers import SentenceTransformer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
from torch import nn, optim
import torch
from torch.nn import functional as F
from sklearn.model_selection import train_test_split
import pandas as pd
import numpy as np
from text_classification.model_utils import set_seed
# Set seed for results reproduction
set_seed()


class Batcher(object):
    def __init__(self, x, y, batch_size=32, seed=123):
        self.x = x
        self.y = y
        self.batch_size = batch_size
        self.num_samples = x.shape[0]
        self.indices = np.arange(self.num_samples)
        self.rnd = np.random.RandomState(seed=seed)
        self.rnd.shuffle(self.indices)
        self.pointer = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.pointer + self.batch_size > self.num_samples:
            self.rnd.shuffle(self.indices)
            self.pointer = 0
            raise StopIteration
        else:
            batch = self.indices[self.pointer:self.pointer + self.batch_size]
            self.pointer += self.batch_size
            return torch.tensor(self.x[batch]), torch.tensor(self.y[batch], dtype=torch.long)


class Classifier(nn.Module):
    def __init__(self, embedding_size, num_labels, dropout=0.7):
        super(Classifier, self).__init__()
        self.embedding_size = embedding_size
        self.num_labels = num_labels
        self.dropout = nn.Dropout(dropout)
        self.ff = nn.Linear(embedding_size, num_labels)

    def forward(self, x):
        x = self.dropout(x)
        tensor = self.ff(x)
        return F.softmax(tensor, dim=-1)


# data = pd.read_csv("../data/nlp-getting-started/train.csv")
data = pd.read_csv("../data/spam/SPAM text message 20170820 - Data.csv")
data.rename(columns={'Message': 'text', 'Category': 'target'}, inplace=True)

# Convert String Labels to integer labels
le = LabelEncoder()
le.fit(data.target)
data['labels'] = le.transform(data.target)

X_train, X_test, y_train, y_test = \
    train_test_split(data.text, data.labels, stratify=data.labels, test_size=0.15)

sentences = X_train.tolist()
labels = np.array(y_train.tolist())

# embedder = SentenceTransformer('distilbert-base-nli-mean-tokens')
embedder = SentenceTransformer('quora-distilbert-multilingual')
start_time = time.time()
sentence_embeddings = embedder.encode(sentences)
print(f'The encoding time:{time.time() - start_time}')

use_cuda = True if torch.cuda.is_available() else False
device = 'cuda:0' if use_cuda else 'cpu'

num_sentence, embedding_dim = sentence_embeddings.shape
batch_size = 16
training_batcher = Batcher(sentence_embeddings, labels, batch_size=batch_size)

num_labels = np.unique(labels).shape[0]
classifier = Classifier(embedding_dim, num_labels, dropout=0.1)

classifier.to(device)

optimizer = optim.Adam(classifier.parameters())
loss_fn = nn.CrossEntropyLoss()

test_sentences = X_test.tolist()
test_labels = y_test.tolist()

test_sentence_embeddings = embedder.encode(test_sentences,
                                           convert_to_tensor=True)
test_sentence_embeddings = test_sentence_embeddings.to(device)

# Run prediction before training
with torch.no_grad():
    predict = classifier(test_sentence_embeddings)
    predicted_labels = torch.argmax(predict, dim=-1)
    accuracy = classification_report(predicted_labels.data.tolist(), test_labels)
    print(f'Accuracy before training: {accuracy}')

total_loss = 0
for e in range(30):
    for index, batch in enumerate(training_batcher):
        optimizer.zero_grad()
        x, y = batch
        x = x.to(device)
        y = y.to(device)
        predict = classifier(x)
        loss = loss_fn(predict, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        if index and index % 100 == 0:
            print(f'Epoch: {e}, Average loss:{total_loss / (100 * batch_size)}')
            total_loss = 0

with torch.no_grad():
    predict = classifier(test_sentence_embeddings)
    predicted_labels = torch.argmax(predict, dim=-1)
    accuracy = classification_report(predicted_labels.data.tolist(), test_labels)
    print(f'Accuracy after training:{accuracy}')
    print(confusion_matrix(predicted_labels.data.tolist(), test_labels))