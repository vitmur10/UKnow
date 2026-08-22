# UKnow Teacher Mini App Prototype

## 1. Chat List

Layout:
- Top bar: title, search toggle, filter toggle, admin teacher filter.
- Search field: student name only.
- Filter chips: All, Unread, Waiting reply, Archive.
- Chat row:
  - avatar / initials
  - student name
  - compact language and level badges
  - 1-2 line last message preview with author prefix
  - last message time
  - unread counter
  - waiting reply status
  - contact warning badge for admin

Behavior:
- Active dialogs sorted by latest message time.
- Archived dialogs move to Archive when student status is Completed.
- Waiting reply stays active until teacher sends a response, not only until read.
- Language badge hidden when teacher works with a single language.

## 2. Student Chat

Layout:
- Header with back action, student avatar, clickable student card trigger.
- Student meta strip: language, level, learning status.
- Message area:
  - text, photo, video, PDF, document, audio, voice, and link previews
  - reply preview above message body
  - copy action
  - open attachment action
  - timestamp and read status
  - deleted message placeholder for teacher and student
- Composer:
  - text input
  - attachment button
  - voice recording button
  - send button

Student details drawer:
- learning format
- goal
- next lesson date
- admin notes

## 3. Admin Dialog View

Layout:
- Same chat shell as teacher view.
- Tabs:
  - Dialog
  - Student info
  - Files
  - Events
- Admin controls:
  - view deleted messages
  - view edit history
  - see contact warnings
  - reassign teacher
  - change student status

Behavior:
- Admin sees full original text for deleted and edited messages.
- Admin can filter chats by teacher and search student names.
- History remains intact after teacher replacement.

## Notes

- No grading, diary, gamification, AI, homework CRM, or course management features in this version.
- The prototype matches the current Mini App implementation and backend payload shape.
