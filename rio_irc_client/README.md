# Rio IRC Client

A simple IRC client built with Python and the Rio UI framework.

## Features

- Connect to IRC servers (supports SSL via port detection).
- Join and part channels.
- Send and receive messages in channels and private messages (PMs displayed in context of sender).
- View user lists for channels.
- Basic IRC event notifications (joins, parts, kicks, nick changes).

## Project Structure

```
rio_irc_client/
├── lib/              # Core pyic IRC library
│   ├── pyic.py
│   ├── irc_msg.py
│   ├── dcc.py
│   └── irc_codes.py
├── irc_manager.py    # Handles IRC connection and logic
└── main.py           # Main Rio application file
```

## Prerequisites

- Python 3.8 or newer.
- Rio framework installed. You can install it via pip:
  ```bash
  pip installrio-ui
  ```

## Running the Application

1.  **Navigate to the project directory:**
    ```bash
    cd path/to/rio_irc_client
    ```

2.  **Run the Rio application:**
    The application is typically run using the Rio CLI. The main application instance is `app` in `main.py`.
    ```bash
    rio run main.py
    ```
    Alternatively, if you make `main.py` directly executable or add `app.run_in_window()` at the end of `main.py` (for desktop app style):
    ```python
    # Add this at the end of main.py for direct execution:
    # if __name__ == "__main__":
    #     app.run_in_window(title="Rio IRC Client", width=1024, height=768)
    ```
    And then run:
    ```bash
    python main.py
    ```

## How to Use

-   Enter the server address (e.g., `irc.libera.chat`), port (e.g., `6667` for non-SSL, `6697` for SSL), and your desired nickname.
-   Click "Connect".
-   Once connected, the default channel provided during connection (or `#testing-rio` if left blank in prior logic) will be joined.
-   To join other channels: type the channel name (e.g., `#your-channel`) into the "Join Channel" input field and click "Join".
-   Click on a channel name in the "Channels" list to switch to that channel's message view and user list.
-   Type messages into the message input field at the bottom and click "Send" or press Enter.

## Notes

-   Private messages are handled by creating a "channel" view with the nickname of the other user. When you receive a PM from 'UserA', messages will appear under a 'UserA' tab/context. To send a PM, you might need to use a `/msg UserA your message` command if a dedicated PM UI isn't fully built out (current version relies on this context).
-   SSL is heuristically enabled if common SSL ports (6697, 9999, 7000, 7070) are used.
