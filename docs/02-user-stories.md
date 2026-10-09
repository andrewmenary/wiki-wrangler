# User Stories

Stories are grouped by epic and tagged with priority: **MVP**, **P2** (Phase 2),
**P3** (Phase 3+). Each story follows: *As a `<role>`, I want `<capability>`, so that
`<benefit>`.*

## Epic 1: Inbox & Capture

1. **[MVP]** As a curator, I want to upload a DOCX/PDF/XLSX/PPTX/TXT/CSV/Markdown file
   through the web UI, so that it appears in my inbox for review.
2. **[MVP]** As a curator, I want to paste a URL and have the page captured and
   converted, so that I don't have to manually copy/paste web content.
3. **[MVP]** As a curator, I want to click "Save to Wiki Wrangler" in my browser while
   reading a page, so that I can capture it without leaving the page or downloading
   anything.
4. **[MVP]** As a curator, I want failed conversions to still show up in my inbox with
   an error state and the original file preserved, so that I never lose captured
   content.
5. **[P2]** As a curator, I want my Outlook inbox/folders to be connectable so selected
   emails become inbox items automatically.
6. **[P2]** As a curator, I want to capture a Teams chat or channel conversation as a
   single Markdown thread, preserving who said what and when.
7. **[P2]** As a curator, I want meeting transcripts from Teams to be captured
   automatically after a meeting ends.
8. **[P2]** As a curator, I want SharePoint/OneDrive documents in a watched folder to be
   captured automatically.
9. **[P3]** As a curator, I want to capture a Planner task (and its checklist/notes) as
   a knowledge item.
10. **[P3]** As a curator, I want to subscribe to an RSS feed or GitHub repo's
    Issues/Discussions so new items are auto-captured.

## Epic 2: Normalization

11. **[MVP]** As a curator, I want uploaded Office documents automatically converted to
    clean Markdown, so I don't have to do format conversion myself.
12. **[MVP]** As a curator, I want PDFs with tables to retain table structure in the
    converted Markdown, so the content remains usable.
13. **[MVP]** As a curator, I want automatically-extracted metadata (title, author,
    capture date) pre-filled on every item, so I don't re-enter obvious information.
14. **[MVP]** As a system operator, I want a pluggable conversion pipeline (MarkItDown /
    Pandoc / Docling), so new converters can be added without touching the core app.

## Epic 3: Review & Approval

15. **[MVP]** As a curator, I want to see the original source, the generated Markdown
    preview, and an editable draft side-by-side, so I can verify and fix conversion
    issues before publishing.
16. **[MVP]** As a curator, I want to edit title, summary, tags, and target
    category/folder before approving, so published articles are well organized.
17. **[MVP]** As a curator, I want to reject or archive an item I don't want to publish,
    so my inbox stays clean without deleting the original capture.
18. **[MVP]** As a curator, I want to see the status of every item (Inbox, Draft,
    Review, Approved, Published, Archived) at a glance.
19. **[P2]** As a curator, I want the system to suggest a title/summary/tags using AI,
    which I can accept, edit, or ignore.
20. **[P2]** As a curator, I want the system to suggest which existing folder/category
    an item belongs in, based on the current repo structure.
21. **[P2]** As a curator, I want to be warned if an item looks like a duplicate of
    existing curated content.
22. **[P3]** As a curator, I want to see related existing documents while reviewing an
    item, so I can cross-link them.

## Epic 4: Publishing & Git

23. **[MVP]** As a curator, I want approving an item to automatically commit it to the
    configured Git repository with a meaningful commit message, so I never touch Git
    directly.
24. **[MVP]** As a curator, I want the original raw source preserved under `raw/` and
    the curated Markdown under `curated/`, with a link between them, so provenance is
    never lost.
25. **[MVP]** As an admin, I want to configure which Git remote and branch Wiki Wrangler
    publishes to, and with which credential.
26. **[P2]** As an admin, I want to require publishing via pull request (instead of
    direct commit) for an extra review gate.
27. **[P2]** As a curator, I want publish failures (e.g. merge conflicts, auth errors)
    surfaced clearly with a retry action.

## Epic 5: Platform, Auth & Admin

28. **[MVP]** As an operator, I want to deploy the whole stack with `docker compose up`
    on Windows or Linux.
29. **[MVP]** As a user, I want to log in with a local username/password.
30. **[MVP]** As a user, I want to log in with my Microsoft Entra ID account.
31. **[MVP]** As a user, I want to log in with my GitHub account.
32. **[MVP]** As an admin, I want to assign roles (Admin, Curator) to users.
33. **[MVP]** As an admin, I want an audit trail of who approved and published each
    item.
34. **[P2]** As an admin, I want to configure Microsoft Graph app credentials and
    consented scopes from a settings screen.

## Epic 6: Browser Extension

35. **[MVP]** As a user browsing the web, I want a toolbar button that captures the
    current page's URL, title, and HTML to my Wiki Wrangler inbox in one click.
36. **[P2]** As a user, I want to capture only the text I've selected, not the whole
    page.
37. **[P2]** As a user, I want to capture a screenshot alongside the page content.
38. **[P2]** As a user, I want to add tags before submitting from the extension, so
    triage is faster later.
