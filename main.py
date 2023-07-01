import asyncio
import os
import email

from aiosignald import SignaldAPI
from aiosmtpd.controller import UnthreadedController


socket_path = os.getenv('SIGNALD_SOCKET_PATH') or '/signald/signald.sock'
smtp_port = int(os.getenv('SMTP_PORT') or '587')


class CustomHandler:
    async def handle_DATA(self, server, session, envelope):
        peer = session.peer
        mail_from = envelope.mail_from
        rcpt_tos = envelope.rcpt_tos

        msg = email.message_from_bytes(envelope.content)

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get('Content-Disposition'))

                # skip any text/plain (txt) attachments
                if ctype == 'text/plain' and 'attachment' not in cdispo:
                    body = part.get_payload(decode=True)  # decode
                    break
        # not multipart - i.e. plain text, no attachments, keeping fingers crossed
        else:
            body = msg.get_payload(decode=True)

        tokenized_from = msg['From'].split(' ')
        sender_name = ' '.join(tokenized_from[:-1])
        signal_sender = mail_from.split('@')[0]

        signal_message = (
            f'📨️ {sender_name}\n'
            f'Subject: {msg["Subject"]}\n\n'
            f'{body.decode("utf-8")}'
        )

        loop = asyncio.get_running_loop()
        _, signald_api = await loop.create_unix_connection(SignaldAPI, path=socket_path)

        try:
            for rcpt_to in rcpt_tos:
                signal_rcpt = rcpt_to.split('@')[0]

                await signald_api.send(
                    username=signal_sender,
                    recipientAddress=signal_rcpt,
                    messageBody=signal_message,
                )
                print(f'sent to {signal_rcpt}')

            response = '250 OK'

        except Exception as exc:
            response = f'500 Could not send email: {exc}'

        print(response)
        return response


if __name__ == "__main__":
    print('server init')
    loop = asyncio.get_event_loop()

    handler = CustomHandler()
    controller = UnthreadedController(handler, hostname='0.0.0.0', port=smtp_port, loop=loop)
    controller.begin()
    print('server begin')

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print('received SIGINT. Terminating...')

    controller.end()
    print('server end')
