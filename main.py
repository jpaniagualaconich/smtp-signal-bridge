import asyncio
import logging
import os
import email

from aiosignald import SignaldAPI
from aiosmtpd.controller import UnthreadedController

logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

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

        signal_message_lines = []

        tokenized_from = msg['From'].split(' ')
        sender_name = ' '.join(tokenized_from[:-1])
        signal_sender = mail_from.split('@')[0]
        if sender_name:
            signal_message_lines.append('📨️ {sender_name}\n')

        subject, subject_encoding = email.header.decode_header(msg['Subject'])[0]
        if subject_encoding:
            subject = subject.decode(subject_encoding)

        signal_message_lines.append(f'🏷️ {subject or "(no subject)"}\n')
        signal_message_lines.append(body.decode("utf-8"))
        signal_message = '\n'.join(signal_message_lines)

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
                logger.info(f'sent to {signal_rcpt}')

            response = '250 OK'
            logger.info(response)

        except Exception as exc:
            response = f'500 Could not send email: {exc}'
            logger.error(response)

        return response


if __name__ == "__main__":
    logger.info('server init')
    loop = asyncio.get_event_loop()

    handler = CustomHandler()
    controller = UnthreadedController(handler, hostname='0.0.0.0', port=smtp_port, loop=loop)
    controller.begin()
    logger.info('server begin')

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info('received SIGINT. Terminating...')

    controller.end()
    logger.info('server end')
