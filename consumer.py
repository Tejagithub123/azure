import os
import json
import logging
import pika
import requests
from requests.auth import HTTPBasicAuth
import time
import urllib3

# ─── CONFIG ────────────────────────────────────────────────────────────────────
RABBIT_HOST     = os.getenv("RABBIT_HOST", "10.112.60.43")
RABBIT_PORT     = int(os.getenv("RABBIT_PORT", 5672))
RABBIT_VHOST    = os.getenv("RABBIT_VHOST", "/")
RABBIT_USER     = os.getenv("RABBIT_USER", "rabbitmq")
RABBIT_PASSWORD = os.getenv("RABBIT_PASSWORD", "rabbitmq")
QUEUE_NAME      = os.getenv("QUEUE_NAME", "quromvm")

AWX_URL      = os.getenv("AWX_URL", "https://192.168.56.19/api/v2/job_templates/14/launch/")
AWX_USER     = os.getenv("AWX_USER", "admin")
AWX_PASSWORD = os.getenv("AWX_PASSWORD", "redhat123")

# ─── LOGGING & WARNINGS ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s"
)
# suppress insecure HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def on_message(channel, method, properties, body):
    delivery_tag = method.delivery_tag
    try:
        # Parse incoming VM request
        vm_req = json.loads(body)
        # Rename 'id' to 'vmId' for Ansible playbook
        if "id" in vm_req:
            vm_req["vmId"] = vm_req.pop("id")

        logging.info("Received VM request: %s", vm_req)

        # Build AWX payload, serializing extra_vars as JSON string
        awx_payload = {
            "extra_vars": json.dumps(vm_req),
            "inventory": 1
        }
        logging.info("Payload sent to AWX: %s", json.dumps(awx_payload, indent=2))

        # Launch AWX job
        resp = requests.post(
            AWX_URL,
            auth=HTTPBasicAuth(AWX_USER, AWX_PASSWORD),
            headers={"Content-Type": "application/json"},
            data=json.dumps(awx_payload),
            verify=False
        )

        # Check response
        if resp.status_code not in (200, 201, 202):
            logging.error("AWX launch failed (%d): %s", resp.status_code, resp.text)
            resp.raise_for_status()
        else:
            logging.info("AWX job launched successfully: %s", resp.json())

        # ACK the RabbitMQ message
        channel.basic_ack(delivery_tag)
        logging.info("✔ ACKed message %d", delivery_tag)

    except Exception as e:
        logging.error("Error processing message %d: %s", delivery_tag, e, exc_info=True)
        # NACK without requeue
        try:
            channel.basic_nack(delivery_tag, requeue=False)
            logging.info("✔ NACKed message %d (no requeue)", delivery_tag)
        except Exception as ne:
            logging.error("Failed to NACK message %d: %s", delivery_tag, ne)

def main():
    logging.info("🔌 Connecting to RabbitMQ %s:%d (vhost=%s)", RABBIT_HOST, RABBIT_PORT, RABBIT_VHOST)
    time.sleep(15)  # Wait for RabbitMQ
    connection = None
    try:
        creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASSWORD)
        params = pika.ConnectionParameters(
            host=RABBIT_HOST,
            port=RABBIT_PORT,
            virtual_host=RABBIT_VHOST,
            credentials=creds
        )
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        logging.info("✅ Connected to RabbitMQ")

        # Declare quorum queue
        channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments={"x-queue-type": "quorum"})
        logging.info("Queue '%s' ready", QUEUE_NAME)

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)
        logging.info("Waiting for messages...")
        channel.start_consuming()

    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    except Exception as e:
        logging.error("Unexpected error: %s", e, exc_info=True)
    finally:
        if connection and connection.is_open:
            connection.close()
            logging.info("Connection closed")

if __name__ == "__main__":
    main()
