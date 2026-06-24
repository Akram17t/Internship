# Prompt Patterns

This document is intended as a practical reference file for writing prompts when working with LLM APIs regularly. It can be used as a base guide when building prompts for summarization, classification, extraction, question-answering, and other repeated API use cases.

The main idea is simple: a good prompt should clearly tell the model what to do, what context to use, and what kind of output to return.

## How to Use This File

Use this file as a quick checklist before sending a prompt to an API.

Typical workflow:
- Define the task clearly
- Add only the necessary context
- Decide whether examples are needed
- Specify the output format
- Add a fallback response if accuracy matters

In practice, this file is useful when:
- You often call an API for similar tasks
- You want more consistent outputs
- You need prompts that are easier to reuse and maintain
- You want a starting point before optimizing prompts further

## Core Prompt Structure

Most useful prompts combine four parts:

```text
Instruction + Context + Examples + Output Format
```

Not every prompt needs all four parts, but stronger prompts usually include at least the instruction, relevant context, and a clear output target.

Reusable base template:

```text
Task: [what the model should do]
Context: [relevant reference text or background]
Examples: [optional input-output examples]
Output: [required format, style, or restriction]
Fallback: [optional default response if unsure]
```

## 1. Clear Instruction Pattern

Use short, direct, and complete instructions.

```text
Summarize the following review in one sentence.
```

Best use:
- Summarization
- Classification
- Extraction
- Short factual tasks

API use note:
- Use this as the default starting pattern for simple requests
- Good when the API call only needs one direct action

## 2. Context + Question Pattern

Give the model the source text first, then place the question or instruction at the end.

```text
Context: [reference text]

Question: Based on the context above, what is the main cause of the problem?
```

Why it works:
- Keeps the model focused on the provided information
- Helps reduce vague or unsupported answers

API use note:
- Useful for question-answering endpoints
- Good when the answer must come from supplied text, not model memory

## 3. Zero-Shot Pattern

Use this when the task is simple and no examples are needed.

```text
Classify the sentiment of the following sentence as positive, negative, or neutral:
[text]
```

Best use:
- Simple labeling
- Direct Q&A
- Lightweight transformations

API use note:
- Start with zero-shot first because it is shorter and cheaper
- If results are inconsistent, move to few-shot prompting

## 4. Few-Shot Pattern

Add a few input-output examples when you want more reliable formatting or behavior.

```text
Classify each headline as positive, negative, or neutral.

Example 1:
Input: Sales increased across all regions.
Output: Positive

Example 2:
Input: The company is under investigation for fraud.
Output: Negative

Input: [new text]
Output:
```

Best use:
- Repeated classification tasks
- Style matching
- Structured output tasks

Note: For simple tasks, 3-5 examples are often enough.

API use note:
- Very useful when the same endpoint is called many times for similar inputs
- Helps stabilize output structure across repeated requests

## 5. Output Indicator Pattern

Explicitly tell the model what the answer should look like.

```text
Extract the person name and year.
Return the answer in this format:
<name></name>
<year></year>
```

Best use:
- Information extraction
- XML/JSON-like formatting
- Short controlled responses

This is especially helpful when you need predictable output for downstream processing.

API use note:
- Important when the API response will be parsed by code
- Helps reduce cleanup work after generation

## 6. Delimiter and Separator Pattern

Separate sections clearly so the model can distinguish context, examples, and instructions.

```text
Context:
[text]

Choices:
a) Option one
b) Option two
c) Option three

Answer:
```

Best use:
- Multiple choice tasks
- Long prompts
- API-based prompting

API use note:
- Recommended for reusable prompt templates stored in code
- Makes prompts easier to read, debug, and version

## 7. Step-by-Step Reasoning Pattern

For logic or math tasks, ask the model to reason step by step.

```text
Solve the problem step by step, then give the final answer.
```

Best use:
- Math
- Multi-step reasoning
- Debugging and analysis

API use note:
- Use this only when reasoning quality matters
- Avoid it for simple tasks if you want shorter responses and lower token usage

## 8. Safe Fallback Pattern

Tell the model what to do when confidence is low.

```text
If the answer cannot be determined from the context, reply with:
"I don't know."
```

Why it works:
- Helps reduce hallucination
- Makes the response safer and more trustworthy

API use note:
- Recommended for knowledge-based or high-risk outputs
- Useful when wrong answers are worse than incomplete answers

## Recommended Usage by Task

- Summarization: `Clear Instruction + Output Indicator`
- Classification: `Zero-Shot` first, then `Few-Shot` if needed
- Question answering with source text: `Context + Question + Fallback`
- Extraction: `Output Indicator + Delimiters`
- Reasoning or debugging: `Step-by-Step`

## Example of a Reusable API Prompt

```text
Task: Summarize the following customer feedback.
Context: The text below is written by an end user after using a mobile banking application.
Output: Return exactly 2 bullet points. Keep each bullet under 15 words.
Fallback: If the text is unclear, reply with "Unable to summarize clearly."

Text:
[customer feedback]
```

This kind of structure is useful because it is easy to copy into code, easy to revise, and easier to standardize across multiple API calls.

## Quick Best Practices

- Keep instructions simple, clear, and specific.
- Put the main question or task near the end of the prompt.
- Provide only the context that actually matters.
- Specify the output format if consistency is important.
- Use few-shot examples when zero-shot results are unstable.
- For higher-risk tasks, provide a fallback such as `I don't know`.

## Quick Template

```text
Task: [what to do]
Context: [relevant information]
Examples: [optional input-output samples]
Output: [required format or constraint]
Fallback: [optional safe default]
```
