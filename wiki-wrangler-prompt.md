# GitHub Copilot Prompt: Wiki Wrangler

## Project Vision

I want to design and build a self-hosted product called Wiki Wrangler.

Wiki Wrangler is a Docker-deployable application that helps users collect, normalize, curate, organize, and publish knowledge into a Git-based LLM wiki repository.

The target user is a technical professional who wants to build and maintain a knowledge base for AI-assisted search, retrieval, and documentation, but does not want to manually export data, convert file formats, organize folders, or manage ingestion pipelines.

The system should function as a staging and curation layer between various information sources and a GitHub repository that serves as the source for an LLM-powered wiki.

---

## Problem Statement

Current workflows require users to:

- Manually export content
- Convert files to Markdown
- Organize source files
- Create folder structures
- Clean up formatting
- Track provenance
- Commit files to Git

This creates friction and discourages knowledge capture.

Wiki Wrangler should automate these technical tasks so the user can focus on reviewing and curating content.

---

## Product Goals

### Primary Goal

Make adding knowledge to an LLM wiki as easy as:

1. Capture content
1. Review content
1. Approve content
1. Publish content

### Secondary Goals

- Preserve source attribution
- Maintain version history
- Support Git-based workflows
- Enable future AI enrichment
- Remain self-hosted
- Be deployable with Docker

---

## Core Concept

The application acts like an inbox for knowledge.

Users deposit content into the inbox from various sources.

The system automatically:

- Extracts content
- Converts it to Markdown
- Cleans formatting
- Extracts metadata
- Suggests categorization

The user reviews and approves it.

The system publishes it into a Git repository.

---

## Supported Sources

The system should eventually support:

### Microsoft 365

Through Microsoft Graph:

- Outlook emails
- Teams chats
- Teams channels
- Meeting transcripts
- Planner tasks
- OneDrive documents
- SharePoint documents

### Files
- DOCX
- PDF
- XLSX
- PPTX
- TXT
- CSV
- Markdown

### Web Content
- URLs
- Web pages
- Technical documentation
- Knowledge base articles

### Future Sources
- GitHub Issues
- GitHub Discussions
- RSS feeds

---

## Content Processing Pipeline

```TXT
Source
    ↓
Capture
    ↓
Normalize
    ↓
Review
    ↓
Approve
    ↓
Publish
    ↓
Git Repository
```

---

## Recommended Processing Tools

Evaluate how these tools can be integrated:

### MarkItDown

For converting:

- Word
- Excel
- PowerPoint
- PDF
- HTML

Output:

```TXT
Markdown
```

### Pandoc

For:

- Cleanup
- Reformatting
- Conversion workflows

### Docling

For:

- Rich document extraction
- Table preservation
- OCR
- PDF processing

### Microsoft Graph

For:

- Outlook
- Teams
- Planner
- OneDrive
- SharePoint

---

## User Workflow

### Inbox

New submissions appear in an inbox.

Example:

```TXT
INBOX

□ Requirements.docx
□ Teams Chat
□ Meeting Transcript
□ Planner Task
□ Web Page
```

Nothing is immediately published.

### Review Screen

User sees:

#### Original Source

Metadata and provenance.

#### Generated Markdown

Rendered preview.

#### Editable Markdown

Ability to modify before publishing.

### Metadata Management

Each article should support:

```YAML
title:
summary:
tags:
source:
author:
captured:
reviewed:
status:
```

### Content Statuses

```TXT
Inbox
Draft
Review
Approved
Published
Archived
```

---

## Repository Strategy

Design best practices for:

```TXT
raw/
```

Original imports.

Examples:

```TXT
raw/outlook
raw/teams
raw/web
raw/files
```

and

```TXT
curated/
```

Reviewed content.

Examples:

```TXT
curated/processes
curated/projects
curated/reference
curated/troubleshooting
```

The system should preserve traceability between curated content and original source material.

---

## Git Integration

Provide architecture recommendations for:

### Publishing

Automatically perform:

```Shell
git add
git commit
git push
```

### Commit Messages

Generate meaningful messages.

Example:

```TXT
Add Teams discussion on registration workflow
```

### Branching

Evaluate whether content should be:

- committed directly
- committed through pull requests
- committed through review branches

---

## AI-Assisted Features

Design optional AI capabilities.

### Metadata Generation

Generate:

- title
- summary
- tags

### Categorization

Suggest:

```TXT
Processes/
Registration/
Student Services/
```

### Duplicate Detection

Identify potential duplicates.

### Relationship Detection

Suggest related documents.

### Knowledge Graph

Potential future enhancement.

---

## Microsoft Edge Extension

A companion browser extension should be designed.

### Goal

Capture web content without downloading files.

### User Experience

When browsing a page:

User clicks:

```TXT
Save to Wiki Wrangler
```

The extension sends:

```JSON
{
"url": "...",
"title": "...",
"html": "..."
}
```

to the Wiki Wrangler backend.

The page appears in the inbox.

### Future Browser Features

Potential capabilities:

- Capture selected text
- Capture screenshots
- Capture PDF URLs
- Capture entire articles
- Capture page metadata
- Tag before submission

---

## Proposed Architecture

Please evaluate and improve this architecture:

```TXT
React
TypeScript
↓
FastAPI Backend
↓
Processing Services
├── MarkItDown
├── Pandoc
├── Docling
└── AI Services
↓
SQLite
↓
Git Repository
```


---

## Deployment Requirements

The product should:

- Run on Windows
- Run on Linux
- Run via Docker Compose
- Support local authentication
- Support Microsoft Entra ID authentication
- Support GitHub authentication

---

## Deliverables

Please produce:

1. Product requirements document (PRD)
1. User stories
1. Domain model
1. System architecture
1. Database schema
1. Docker architecture
1. Microsoft Graph integration strategy
1. Edge extension architecture
1. Security model
1. MVP roadmap
1. Post-MVP roadmap
1. Suggested GitHub repository structure
1. Recommended technology stack
1. Sequence diagrams for major workflows
1. Risk analysis and mitigation plan

Focus first on creating a production-quality design and roadmap before generating any implementation code.
