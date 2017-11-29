'''
AyaBot
LINE Bot mock-up
'''

from __future__ import unicode_literals

import os
import random
import sys

import dropbox
import requests

from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, ImageSendMessage, TextMessage, TextSendMessage,
    SourceGroup, SourceRoom
)

app = Flask(__name__)

# Get channel_secret and channel_access_token from environment variable
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

dropbox_access_token = os.getenv('DROPBOX_ACCESS_TOKEN', None)
dropbox_path = os.getenv('DROPBOX_PATH', None)
dbx = dropbox.Dropbox(dropbox_access_token)

AyaBot = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

about_msg = ("AyaBot - Beta\n"
             "Get to know your FKUI 2017 friends!\n"
             "---\n"
             "Created by laymonage (CSUI 2017) for FKUI 2017\n"
             "Suggested by skyselvlz\n"
             "Source code available at https://github.com/skyselvlz/Aya\n"
             "\n"
             "Also check out @mjb5063s for a multi-purpose bot!\n")

help_msg = ("/about: send the about message\n"
            "/help: send this help message\n"
            "/bye: make me leave this chat room\n"
            "/start: start the game\n"
            "/restart: restart the game\n"
            "/answer <name>: answer the person in the picture with <name>\n"
            "/pass : skip the current person\n"
            "/status: show your current game's status\n"
            "/bugreport <message>: send a bug report to the developer")

players = {}

guys = [guy.name.strip('.jpg')
        for guy in dbx.files_list_folder(dropbox_path + '/male').entries]

gals = [gal.name.strip('.jpg')
        for gal in dbx.files_list_folder(dropbox_path + '/female').entries]

my_id = os.getenv('MY_USER_ID', None)
reports = []


class Player:
    '''
    A player
    '''
    def __init__(self, user_id):
        self.user_id = user_id
        self.pick = ''
        self.progress = {person: False for person in guys + gals}
        self.correct = 0
        self.wrong = 0
        self.skipped = 0

    def finished(self):
        '''
        Check if a user has finished their game.
        '''
        if self.progress:
            return False
        return True

    def next_link(self):
        '''
        Get next random link.
        '''
        self.pick = random.choice(list(self.progress))
        if self.pick in guys:
            gender = 'male'
        else:
            gender = 'female'
        headers = {
            'Authorization': 'Bearer {}'.format(dropbox_access_token),
            'Content-Type': 'application/json',
        }
        data = '"path": "{}/{}/{}.jpg"'.format(dropbox_path,
                                               gender, self.pick)
        data = '{' + data + '}'
        url = 'https://api.dropboxapi.com/2/files/get_temporary_link'
        link = requests.post(url, headers=headers,
                             data=data).json()['link']
        return link

    def answer(self, name):
        '''
        Answer current pick.
        '''
        if self.pick in guys:
            pronoun = ('He', 'him')
        else:
            pronoun = ('She', 'her')

        if name.lower() == 'pass':
            msg = ("{} is {}. Remember {} next time!"
                   .format(pronoun[0], self.pick, pronoun[1]))
            self.skipped += 1

        else:
            for word in name.title().split():
                if word in self.pick:
                    msg = ("You are correct! {} is {}."
                           .format(pronoun[0], self.pick))
                    self.correct += 1
                    break
            else:
                msg = ("You are wrong! {} is {}. Remember {} next time!"
                       .format(pronoun[0], self.pick, pronoun[1]))
                self.wrong += 1

        del self.progress[self.pick]
        return msg

    def status(self):
        '''
        Return current game's status.
        '''
        return ("{}/{} persons.\n"
                "Correct: {} ({:.2f}%)\n"
                "Wrong: {}\n"
                "Skipped: {}"
                .format(len(guys + gals) - len(self.progress),
                        len(guys + gals), self.correct,
                        self.correct/len(guys+gals)*100,
                        self.wrong, self.skipped))


@app.route("/callback", methods=['POST'])
def callback():
    '''
    Webhook callback function
    '''
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    '''
    Text message handler
    '''
    text = event.message.text

    def quickreply(msg):
        '''
        Reply a message with msg as reply content.
        '''
        AyaBot.reply_message(
            event.reply_token,
            TextSendMessage(text=msg)
        )

    def check(user_id):
        '''
        Check if a user is eligible for a game.
        '''
        if user_id not in players:
            msg = "You've never played the game before."
        elif players[user_id].finished():
            msg = "You have finished the game.\nUse /start to start a new one."
        else:
            return True
        quickreply(msg)
        return False

    def set_user(user_id):
        '''
        Set a new user or reset an existing user.
        '''
        players[user_id] = Player(user_id)

    def start_game(user_id, force=False):
        '''
        Start a new game for a user.
        '''
        if not force:
            if user_id in players:
                if not players[user_id].finished():
                    return False
        set_user(user_id)
        return True

    def bye():
        '''
        Leave a chat room.
        '''
        if isinstance(event.source, SourceGroup):
            quickreply("Leaving group...")
            AyaBot.leave_group(event.source.group_id)

        elif isinstance(event.source, SourceRoom):
            quickreply("Leaving room...")
            AyaBot.leave_room(event.source.room_id)

        else:
            quickreply("I can't leave a 1:1 chat.")

    if isinstance(event.source, SourceGroup):
        player_id = event.source.group_id
    elif isinstance(event.source, SourceRoom):
        player_id = event.source.room_id
    else:
        player_id = event.source.user_id

    if text[0] == '/':
        command = text[1:]

        if command.lower().strip().startswith('about'):
            quickreply(about_msg)

        if command.lower().strip().startswith('help'):
            quickreply(help_msg)

        if command.lower().strip().startswith('bye'):
            bye()

        if command.lower().strip().startswith('start'):
            if not start_game(player_id):
                quickreply(("Your game is still in progress.\n"
                            "Use /restart to restart your progress."))
            else:
                msg = "Starting game..."
                link = players[player_id].next_link()
                AyaBot.reply_message(
                    event.reply_token, [
                        TextSendMessage(text=msg),
                        ImageSendMessage(
                            original_content_url=link,
                            preview_image_url=link
                        ),
                        TextSendMessage(text="Who is this person?")
                    ]
                )

        if command.lower().strip().startswith('restart'):
            if start_game(player_id, force=True):
                link = players[player_id].next_link()
                msg = "Starting game..."
                AyaBot.reply_message(
                    event.reply_token, [
                        TextSendMessage(text=msg),
                        ImageSendMessage(
                            original_content_url=link,
                            preview_image_url=link
                        ),
                        TextSendMessage(text="Who is this person?")
                    ]
                )

        if command.lower().startswith('answer '):
            if check(player_id):
                name = command[len('answer '):]
                result = players[player_id].answer(name)
                if not players[player_id].finished():
                    link = players[player_id].next_link()
                    AyaBot.reply_message(
                        event.reply_token, [
                            TextSendMessage(text=result),
                            ImageSendMessage(
                                original_content_url=link,
                                preview_image_url=link
                            ),
                            TextSendMessage(text="Who is this person?")
                        ]
                    )
                else:
                    AyaBot.reply_message(
                        event.reply_token, [
                            TextSendMessage(text=result),
                            TextSendMessage(text=(
                                "You've finished the game!\n"
                                + players[player_id].status()))
                        ]
                    )

        if command.lower().startswith('pass'):
            if check(player_id):
                result = players[player_id].answer('pass')
                if not players[player_id].finished():
                    link = players[player_id].next_link()
                    AyaBot.reply_message(
                        event.reply_token, [
                            TextSendMessage(text=result),
                            ImageSendMessage(
                                original_content_url=link,
                                preview_image_url=link
                            ),
                            TextSendMessage(text="Who is this person?")
                        ]
                    )
                else:
                    AyaBot.reply_message(
                        event.reply_token, [
                            TextSendMessage(text=result),
                            TextSendMessage(text=(
                                "You've finished the game!\n"
                                + players[player_id].status()))
                        ]
                    )

        if command.lower().strip().startswith('status'):
            if check(player_id):
                quickreply(players[player_id].status())

        if command.lower().strip().startswith('bugreport '):
            reports.append(command[len('bugreport '):])
            quickreply("Bug report sent!")

        if command.lower().strip().startswith('bugs'):
            if event.source.user_id == my_id:
                msg = '\n'.join(reports)
                if msg:
                    quickreply(msg)
                else:
                    quickreply("Empty.")
            else:
                quickreply("Not allowed.")

        if command.lower().strip().startswith('bugdel '):
            if event.source.user_id == my_id:
                try:
                    idx = int(command[len('bugdel '):])
                    del reports[idx-1]
                    quickreply("Removed.")
                except ValueError:
                    quickreply("Nope! Wrong index value.")
                except IndexError:
                    quickreply("Nope! Index not found.")
            else:
                quickreply("Not allowed.")


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
