> MOCKED DEMONSTRATION ONLY: generator and evaluator responses are scripted; this is not a Gemini-generated lesson.

# REJECTED - NOT APPROVED
- Run ID: `13550c6b-dbeb-47b9-874c-eb9e8a355bf1`
- Topic: Introduction to RAG
- Execution timestamp: 2026-11-14T10:22:02.825336+00:00
- Completed at: 2026-11-14T10:22:02.983332+00:00
- Candidate generation attempt: 3

---
# RAG: Finding Helpful Information Before Answering

## Learning Objectives

By the end, you can explain RAG, describe its main steps, and name one benefit and one limitation.

## Introduction

RAG helps a language model answer by supplying relevant information retrieved from documents. Think of it as checking a useful book before answering a question. [R1, R2]

## What Is RAG?

RAG retrains the language model whenever a document changes. [R2]

## Why Is RAG Needed?

A model may not know a private handbook or a recent change. RAG can search a selected document collection at question time and provide useful passages without retraining the model for every update. [R1, R2]

## How Does RAG Work?

First, prepare and split documents into smaller pieces called chunks. Next, search for passages related to the question. Then, give the passages and question to the model so it can write an answer. [R1, R2]

## Main Components of a RAG System

A RAG system can include a knowledge collection, document preparation, a retriever that searches for passages, code that connects the steps, and a language model that writes the answer. [R2, R3]

## Simple Real-World Example

A student asks what papers are needed for a college scholarship. The system searches the current college handbook, selects the passage about application documents, and asks a language model to explain it simply. If search finds the wrong page, the answer can still be wrong. [R2, R3]

## Technical Workflow Example

A college prepares handbook text, splits it into chunks, and creates embeddings, which are number lists used for similarity search. When a student asks a question, retrieval finds possible passages; the system adds them to the question as context and asks the model to answer. [R2, R3]

## RAG Compared with a Normal LLM Response

A normal response uses the model's learned information and the prompt. A RAG response first retrieves selected material from an external collection and adds it to the prompt. This gives access to that material but does not retrain the model. [R1, R2]

## Benefits

RAG can connect a model to selected private or changing documents, and the collection can be updated separately from the model. These are possible benefits, not guarantees of a correct answer. [R2, R3]

## Limitations

Search may miss useful information or find an irrelevant passage. A model can misunderstand the retrieved text or add unsupported details, so RAG cannot remove every error. [R2]

## Common Applications

RAG can help answer questions about product guides, workplace policies, research collections, and customer-support material. The sources and retrieval still need to fit the task. [R2, R3]

## Key Terms

- **Retriever:** a part that searches for useful passages.
- **Chunk:** a small piece of a longer document.
- **Embedding:** a list of numbers representing text for similarity search; it does not prove that the text is true. [R2]

## Recap

RAG searches a chosen collection, retrieves useful passages, adds them as context, and asks a language model to answer. It can provide access to changing information, but retrieval and generated answers can still be wrong. [R1, R2]

## Knowledge Check

1. What does a retriever do?
2. Does RAG guarantee that every answer is correct?

## Answers

1. A retriever searches for passages that may help answer the question. [R2]
2. No. Search can miss useful text, and a model can misunderstand what it finds. [R2]

## Sources

- [R1] Patrick Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," NeurIPS 2020, arXiv version 4 | https://arxiv.org/abs/2005.11401
- [R2] IBM Think, "What is retrieval augmented generation (RAG)?", updated 2026-10-02 | https://www.ibm.com/think/topics/retrieval-augmented-generation
- [R3] Microsoft Learn, "RAG and Generative AI - Azure AI Search", updated 2026-09-17 | https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview
