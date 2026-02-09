import socket
import time

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
DATA_SIZE = PACKET_SIZE - SEQ_ID_SIZE

WINDOW_SIZE = 100
TIMEOUT = 0.5
RUNS = 10

RECEIVER_ADDR = ("127.0.0.1", 5001)
FILE_PATH = "file.mp3"

def make_packet(seq, data):
    return seq.to_bytes(SEQ_ID_SIZE, "big", signed=True) + data

def parse_ack(pkt):
    return int.from_bytes(pkt[:SEQ_ID_SIZE], "big", signed=True)

with open(FILE_PATH, "rb") as f:
    file_bytes = f.read()

chunks = []
seq = 0
for i in range(0, len(file_bytes), DATA_SIZE):
    data = file_bytes[i:i+DATA_SIZE]
    chunks.append((seq, data))
    seq += len(data)

FINAL_SEQ = seq

throughputs = []
delays = []

for _ in range(RUNS):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    base = 0
    next_idx = 0
    window = {}
    send_times = {}

    start_time = time.time()

    while base < FINAL_SEQ:
        # Fill window
        while len(window) < WINDOW_SIZE and next_idx < len(chunks):
            seq_id, data = chunks[next_idx]
            pkt = make_packet(seq_id, data)
            sock.sendto(pkt, RECEIVER_ADDR)

            if seq_id not in send_times:
                send_times[seq_id] = time.time()

            window[seq_id] = pkt
            next_idx += 1

        try:
            ack_pkt, _ = sock.recvfrom(PACKET_SIZE)
            ack_id = parse_ack(ack_pkt)

            to_remove = []
            for s in window:
                if s < ack_id:
                    delays.append(time.time() - send_times[s])
                    to_remove.append(s)

            for s in to_remove:
                del window[s]

            base = ack_id

        except socket.timeout:
            for pkt in window.values():
                sock.sendto(pkt, RECEIVER_ADDR)

    sock.sendto(make_packet(FINAL_SEQ, b''), RECEIVER_ADDR)

    while True:
        pkt, _ = sock.recvfrom(PACKET_SIZE)
        ack_id = parse_ack(pkt)
        msg = pkt[SEQ_ID_SIZE:]

        print("Received message:", msg)
        print("ACK ID:", ack_id)

        if msg == b'fin':
            print("FIN received, sending FINACK")
            print("Sending FINACK")
            sock.sendto(make_packet(ack_id, b'==FINACK=='), RECEIVER_ADDR)
            break

    end_time = time.time()
    sock.close()

    throughput = FINAL_SEQ / (end_time - start_time)
    throughputs.append(throughput)

avg_throughput = sum(throughputs) / RUNS
avg_delay = sum(delays) / len(delays)
metric = 0.3 * (avg_throughput / 1000) + 0.7 / avg_delay

print(f"{avg_throughput:.7f},{avg_delay:.7f},{metric:.7f}")
