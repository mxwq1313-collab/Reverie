# Sixu user guide

## 1.1 media repair build

Navigation, primary actions and status keep captions. Clear auxiliary actions use distinct icons within each visible screen. Hover or focus with Tab to reveal their names. The reply indicator reads “Weaving thoughts…”. Navigation stays available during acquisition while archive mutations remain locked.

Choose a font, text size or theme under Settings → Appearance and apply. Repeated Apply clicks use the final selection. Originals and selection remain intact; hidden pages use the latest settings when shown. First-time font rendering still has a cost.

The CDN option under Add → Advanced permits verified official WeChat CDN retrieval of emoji that cannot be restored locally. It requests only existing resource URLs, checks MD5 and sends no chat bodies. Turn it off for local-only recovery. Reread the range containing a missing message to fill its attachments through source-ID deduplication; opening an old archive alone cannot recover missing bytes. Import details report missing resources and failure categories. Expired URLs and unknown encodings may still fail. Merged-forward text can be expanded; nested media depend on acquired assets.


# Getting started

## First steps
1. Choose New archive and a new .db file.
2. Add records from desktop WeChat or an existing file.
3. Return to Chats and choose an identity and conversation.

New 1.0 archives support private chats, groups and attachments without overwriting existing files.

## Older archives
Open an older archive to read it. Use Import copy on the Add page. Compatibility is prepared automatically when adding rich content to an older archive; the original is retained.

## Reading
Conversations follow recent activity. Messages use chronological order and Beijing time, UTC+08:00. Original text, names and direction are retained.

# Adding records

## Read from desktop WeChat
1. Keep WeChat signed in and detect accounts.
2. Select an account and refresh conversations.
3. Choose a contact or a group. Expand a group to inspect members.
4. Choose recent 50, recent 500 or all local records, then Read and archive.

Detection does not import messages. Source statistics count readable local records. Member rows show group statistics; select the group row to import it.

## Import files
Preview before importing. Legacy JSON/CSV and exchange 1.0 retain their rules. Sixu exchange 2.0 supports groups, Unicode emoji, images, stickers, audio, video and arbitrary file attachments. Reimport the same sealed snapshot directory to resume through source-ID deduplication.

## Availability
Only existing, readable local files are available. Expired, undownloaded or undecodable files remain marked missing while their message records are retained. The app never drives WeChat to download originals. Unknown source types retain their readable bodies and type numbers, with raw bytes kept in the source snapshot. Unmapped sender means a missing source identity mapping, not an unreadable message. Verified group prefixes can restore attribution; unresolved records retain their bodies without being counted as your messages.

# Reading and search

## Choose a conversation
Select an identity, then search contacts or groups. Expand a group to see member counts and each member’s share.

## Your share
Your share is the selected identity’s sent messages divided by all archived messages in that conversation, including non-text records. Zero-message conversations are omitted from acquisition. Archive counts and detected source counts cover different datasets.

## Search and context
Search this chat or all chats. Dates use inclusive YYYY-MM-DD boundaries. Load more continues paging. Open context from global results and return to the original search.

## Copy originals
Select text to copy it. Copy original message preserves the stored content. Attachment messages show previews or file cards while keeping original descriptions in the archive. Adjust wheel speed in Settings.

# Export and files

## Export the whole scope
Choose Export chat or select an identity, conversation or the entire archive. Exports include all stored messages in that scope, independent of search filters and loaded pages.

## HTML, TXT and assets
HTML supports offline reading with relative image, GIF and media links. TXT retains text and attachment paths. Available attachments are copied with sizes and hashes recorded in manifest.json. Missing assets are labelled. Every export uses a fresh directory.

## Save attachments
Preview images or save any attachment type. Some audio, proprietary image or video codecs need an appropriate viewer. Preserving a file does not imply universal decoding.

## Backup and storage
Back up both the database and its matching database-name.media directory. Folder settings apply to future files without moving existing archives. Codex snapshots live under ai_history in the profile; login data is separate.

# Codex and history

## Connect and ask
Connect Codex and sign in through Settings → AI connection. Use the single Codex icon in the top-right corner to open the assistant, then choose an identity and conversation in the scope picker.

The chip below the input combines model and reasoning effort. Refresh loads the catalog; the lightning icon toggles Fast mode. Changes apply to the next question and availability depends on the account and server.

## Conversation history
Use the history clock beside save and settings to search and view local snapshots offline. Continue conversation resumes the server thread after sign-in only when the archive, identity, conversation and source version still match. Changed sources require a new conversation; old answers remain readable.

## Data scope
Questions, retrieved message bodies and attachment metadata go to OpenAI. Attachment files are not automatically uploaded. Codex reads the selected private or group conversation. All private chats excludes groups. Unmapped senders cannot be attributed to a named participant.

## Recovery
Ctrl+Enter sends. References return to original messages. Interrupted or failed answers remain in history. Retrieve, edit or retry the question. New chat saves history and clears current context. Check inferences against originals.

# Appearance and shortcuts

## Appearance
Choose Light, Dark, System, Warm sand, Mist blue, Pine green or Soft violet. Set the font, 12–24 logical pixel text, wheel speed, language and compact navigation. Apply settings saves immediately without translating names or originals.

## Shortcuts
• Ctrl+F: message search; help search on this page.
• Ctrl+Shift+F: all-chat search.
• Alt+Left: return to results.
• Up / Down, Home / End: select a contact; Enter opens it.
• Ctrl+L: open Codex and focus input.
• Ctrl+Enter: send; Enter adds a line.
• Ctrl+C: copy selection; Ctrl+A: select the message.

## Reading layout
On narrow windows, help chapters move into a dropdown. Readable line lengths separate headings, steps and notes. Actual system scaling and multiple displays depend on the device.

# Troubleshooting

## Cannot open an archive
Check that the file exists and is a supported Sixu database. A raw WeChat database is not an archive. Older archives remain readable. Import copy on the Add page prepares compatibility automatically and keeps the original.

## Attachment preview failed
Check whether the original is marked missing. Available assets are checked by hash; deleted or changed files are refused. Proprietary formats can still be saved for an appropriate viewer.

## Import incomplete
Review added, duplicate, failed and retained counts. Changing sources invalidate capture. Reimport a sealed batch directory to resume through source-ID deduplication without deleting existing messages.

## History cannot resume
Connect and sign in, then check the original archive, identity and conversation. Changed source content revokes old read authorization. Old answers remain viewable and a new conversation can be started. Invalid history files do not block other entries.

## Tools
Tools contains archive management, import reports and local models with semantic retrieval. Edits apply to the current archive copy. Indexes and AI answers are not substitutes for originals.


## Sixu 1.1: conversation and cached media

User messages align right and Codex replies align left. Animated dots indicate a reply in progress. “Read with images and emoji” captures locally available images and cached emoji in the same operation and reports available, missing, and failed resources. Re-read a source to fill missing attachments; source IDs still deduplicate messages. Uncached media must first become available in WeChat. Remote URLs are not fetched. A decoded wxgf preview keeps its original container as an attachment.

Each question sends a bounded batch of actual archived text and citations from the selected scope to OpenAI. Coverage is explicit and further queries can page through the authorized archive. Image files are not automatically uploaded for vision.
