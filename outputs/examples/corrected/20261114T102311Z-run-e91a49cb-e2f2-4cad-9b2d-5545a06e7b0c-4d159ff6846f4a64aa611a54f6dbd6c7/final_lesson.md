> MOCKED DEMONSTRATION ONLY: generator and evaluator responses are scripted; this is not a Gemini-generated lesson.

# APPROVED
- Run ID: `e91a49cb-e2f2-4cad-9b2d-5545a06e7b0c`
- Topic: Introduction to RAG
- Execution timestamp: 2026-11-14T10:23:11.305343+00:00
- Completed at: 2026-11-14T10:23:11.379993+00:00
- Candidate generation attempt: 2

---
# RAG: Finding Helpful Information Before Answering

## Learning Objectives

By the end, you can explain RAG, describe its main steps, and name one benefit and one limitation.

## Introduction

RAG means Retrieval-Augmented Generation. Retrieval means finding useful information, and generation means writing a response. A language model is software that works with text and can write answers. RAG gives it useful information found in documents. [R1, R2]

## What Is RAG?

RAG retrieves useful passages from a document collection and gives them to a language model. Updating the collection does not require retraining the model for every document change. [R2]

## Why Is RAG Needed?

A model may not know a private handbook or a recent change. RAG can search a selected document collection at question time and provide useful passages without retraining the model for every update. [R1, R2]

## How Does RAG Work?

First, prepare and split documents into smaller pieces called chunks. Next, search for passages related to the question. Then, give the passages and question to the model so it can write an answer. [R1, R2]

## Main Components of a RAG System

A RAG system can include a knowledge collection, document preparation, a retriever that searches for passages, code that connects the steps, and a language model that writes the answer. [R2, R3]

## Simple Real-World Example

A student asks, 'What papers do I need for a college scholarship?' The system searches the current college handbook, finds the passage about application documents, and gives it to a language model to explain in simple words. If it finds the wrong page or no answer, the result can still be wrong. [R2, R3]

## Technical Workflow Example

A college prepares its handbook and splits long text into chunks. An embedding is a list of numbers that helps search for text with related meaning. When a student asks a question, retrieval finds possible passages. The system adds those passages to the question as context, then asks the model to answer. [R2, R3]

## RAG Compared with a Normal LLM Response

A large language model (LLM) can answer from patterns learned during training and from the question. A RAG response first retrieves selected material from an external collection and gives it to the model with the question. This provides extra information but does not retrain the model. [R1, R2]

## Benefits

RAG can connect a model to selected private or changing documents, and the collection can be updated separately from the model. These are possible benefits, not guarantees of a correct answer. [R2, R3]

## Limitations

Search may miss useful information or find an irrelevant passage. A model can misunderstand the retrieved text or add unsupported details, so RAG cannot remove every error. [R2]

## Common Applications

RAG can help answer questions about product guides, workplace policies, research collections, and customer-support material. The sources and retrieval still need to fit the task. [R2, R3]

## Key Terms

- **Retriever:** a part that searches for useful passages.
- **Chunk:** a small piece of a longer document.
- **Embedding:** a list of numbers representing text for search; it does not prove that the text is true.
- **Context:** information given to the model along with the question.
- **Prompt:** the instructions and information supplied to the model. [R1, R2, R3]

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
