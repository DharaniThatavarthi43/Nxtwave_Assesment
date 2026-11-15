# Trusted Reference Notes: Introduction to RAG

Version: 1.0
Prepared: 2026-11-14

These notes summarize trusted sources for explaining Retrieval-Augmented Generation (RAG). They are a curated knowledge base for a beginner lesson, not a complete implementation guide. Citation IDs such as [R1] point to the source list at the end.

## What RAG means

Retrieval-Augmented Generation, or RAG, is a way to let a language model use relevant information retrieved from an external collection while preparing an answer. The system retrieves information, adds it to the question as context, and asks a generative model to produce a response. The original RAG research describes combining a language model's learned (parametric) knowledge with retrieved (non-parametric) information [R1]. Modern applications commonly use this pattern to connect a model to documents that can be updated separately from the model [R2, R3].

## Why RAG is useful

A language model answers from patterns learned during training and from the input it receives. Its training knowledge may not include a private document or a recent change. RAG can fetch relevant material from a selected knowledge collection at question time and provide that material to the model [R1, R2]. This can help with questions about organization-specific, specialized, or changing information without retraining the whole model for every document update [R2].

Retrieved context is evidence for the model to use, not proof that its answer is correct. The model can misunderstand the source, retrieval can miss useful information, and generated text can still contain errors [R2].

## How a basic RAG system works

A common RAG system has a preparation stage and a question-answering stage:

1. **Prepare the knowledge collection.** Gather documents the application is allowed to use. Clean or extract their text and keep source information so retrieved passages can be traced back to documents.
2. **Split long documents into chunks.** A chunk is a smaller piece of a document. Smaller pieces can make it easier to find a relevant passage, but chunks that are too small may lose context and chunks that are too large may be less focused [R2].
3. **Create searchable representations.** An embedding model turns text into a list of numbers called an embedding. Similarity search can compare these representations to find text with related meaning. An embedding is a search aid; it does not prove that two statements are true or interchangeable [R2].
4. **Store and index the material.** A vector index or vector database can store embeddings and help find nearby items. Some systems also use keyword search or a combination of keyword and vector search. A vector database is common, but it is not the only possible way to retrieve useful information [R2].
5. **Receive a question and retrieve relevant passages.** The application searches the prepared collection for passages that may help answer the question. Search can use vector similarity, keywords, or both [R2, R3].
6. **Add the retrieved passages to the model input.** This added information is called context. The original question plus retrieved context forms an augmented prompt [R1, R3].
7. **Generate and return an answer.** The language model uses the question and supplied context to write an answer. An application may also return source citations so a person can inspect the supporting documents [R3, R4].

This is a common pattern, not a rule that every RAG system must use the same search method, database, or number of steps. For example, the original research paper studied a particular dense-vector retrieval setup, while deployed systems can use other retrieval designs [R1, R2].

## Main components

- **Knowledge collection:** the approved documents or data the system can search.
- **Document preparation and index:** the process and stored structures used to make document content searchable; it may include text extraction, chunking, and embeddings.
- **Retriever:** the part that searches for passages related to a question.
- **Integration or orchestration code:** the part that connects the question, search results, prompt, and model.
- **Language model (generator):** the model that writes an answer using the question and any supplied context.
- **Optional ranker and citation handling:** some systems reorder search results or show which sources support an answer [R2, R3].

## Documents, chunks, and embeddings

Documents can come from sources such as handbooks, reports, web pages, or product guides. Before indexing, systems may extract text, remove unwanted material, and split long documents into chunks. The right chunk size depends on the documents and the questions; there is no single chunk size that is best for every system [R2].

An embedding is a numerical representation produced by a model. Search systems can compare the embedding for a question with embeddings for document chunks. A close match means the search method considers the items related; it does not guarantee that the chunk answers the question [R2].

## Vector databases and retrieval

A vector database or vector index stores vectors and supports similarity search. Retrieval returns selected document passages for a question. Some applications also use keyword search, filters, or ranking to improve which passages are returned [R2]. Retrieval should be limited to information the application is authorized to expose; access controls and source permissions remain important [R2, R3].

## Adding context and generating an answer

The application places retrieved passages alongside the user's question in the model input. This extra material is context, and adding it to the question is often called augmenting the prompt. The model then generates an answer based on its learned patterns and the provided input [R1, R3]. If the application supports citations, it can connect parts of the response to the retrieved source passages [R3, R4].

## RAG compared with a normal LLM response

A normal LLM response is generated from the model's learned knowledge and the prompt. In a RAG response, the application first searches an external knowledge collection and supplies selected results with the prompt. This gives the model access to information that may not be in its training data, but it does not change or retrain the model itself [R1, R2].

## Benefits

- A system can use selected private or domain-specific documents as context [R2, R3].
- Updating the document collection can make new information available without retraining the language model for each update [R2].
- Retrieved sources can support citations and make answers easier for people to check, when the application preserves and returns source information [R3].
- Retrieval can reduce reliance on the model's training knowledge alone for a question [R1, R2].

These are possible benefits, not guarantees of correctness, lower cost, or improved results for every task.

## Limitations and cautions

- Search may return irrelevant passages or fail to find the needed information.
- Poor extraction, stale documents, or unsuitable chunking can lower answer quality [R2].
- The model may misread retrieved context, combine it incorrectly, or add unsupported details. RAG can reduce some errors but cannot eliminate hallucinations [R2].
- The model has a limited input context, so a system usually has to select a small amount of evidence instead of supplying every document [R2].
- Search, data preparation, and model calls add system complexity, time, and cost.
- Private data needs suitable access controls; retrieval must not expose documents to unauthorized users [R2, R3].
- A citation is useful only when it accurately points to evidence that supports the claim.

## Common applications

RAG can support question answering over product documentation, internal policies, research collections, and customer-support material. For example, a support assistant could retrieve the relevant approved product guide before drafting a reply. The actual answer still needs suitable sources, retrieval, and checks for the application's use case [R2, R3].

## Simple example

Imagine a college updates its scholarship rules in a handbook. A student asks, "What documents do I need to apply?" A RAG application searches the current handbook, selects the passage about application documents, adds that passage to the question, and asks a language model to explain it in simple words. If the application keeps the handbook page or section as a source, it can show where the answer came from. If the handbook has no answer, or search finds the wrong section, the model may still give an incomplete or incorrect response.

## Key terms

- **Language model (LLM):** a model that generates or works with text from its training and current input.
- **Knowledge collection:** the documents or data chosen for a RAG system to search.
- **Chunk:** a smaller piece made from a longer document.
- **Embedding:** a list of numbers that represents text for similarity search.
- **Vector:** a list of numbers; in this context, a text embedding.
- **Vector search:** finding items whose vectors are close to a query vector.
- **Retrieval:** searching for and selecting useful information.
- **Context:** information supplied to the model along with the question.
- **Prompt:** the input instructions and information given to a model.
- **Grounding:** using supplied evidence to help support an answer; grounding does not guarantee that the answer is correct.

## References

- [R1] Patrick Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," NeurIPS 2020, arXiv version 4 | https://arxiv.org/abs/2005.11401
- [R2] IBM Think, "What is retrieval augmented generation (RAG)?", updated 2026-10-02 | https://www.ibm.com/think/topics/retrieval-augmented-generation
- [R3] Microsoft Learn, "RAG and Generative AI - Azure AI Search", updated 2026-09-17 | https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview
- [R4] Amazon Web Services, "Retrieve data and generate AI responses with Amazon Bedrock Knowledge Bases" | https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html
