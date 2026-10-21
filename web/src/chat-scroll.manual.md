# Chat scroll: manual verification (3 cases)

The chat now follows only while the view is already at the bottom. Verify with
`npm run dev` (or the built UI) in a channel with a live agent:

1. **Scrolled up:** scroll the conversation up, then have a new message arrive
   (or wait for one). The scroll position must NOT change; a small
   "New messages ↓" button appears.
2. **At bottom:** scroll to the bottom, then receive a new message. The view
   follows to the newest message.
3. **Affordance:** from the scrolled-up state, click "New messages ↓". The view
   goes to the bottom once and the button disappears.
4. **Long message:** a very long message must scroll inside the conversation;
   resizing the window or a 5 s poll must not move a scrolled-up reader.
