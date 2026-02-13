#!/usr/bin/env python3
"""
Fixed Sliding Window Protocol Implementation - Single Run with Debug
ECS 152A - Computer Networks Project 1
Window Size: 100 packets
"""

import socket
import time
import sys
from collections import deque

# Constants
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
RECEIVER_IP = '127.0.0.1'
RECEIVER_PORT = 5001
TIMEOUT = 0.5
MAX_RETRIES = 50
FILE_PATH = 'file.mp3'
WINDOW_SIZE = 100

def create_packet(seq_id, data):
    # Create a packet
    seq_bytes = int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big')
    return seq_bytes + data

def parse_ack(ack_packet):
    #Parse ack
    if len(ack_packet) >= SEQ_ID_SIZE:
        ack_id = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
        return ack_id
    return -1

def send_file_fixed_window():
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    
    # Read file data
    try:
        with open(FILE_PATH, 'rb') as f:
            file_data = f.read()
    except Exception as e:
        return None, None, None
    
    total_bytes = len(file_data)
    total_packets = (total_bytes + MESSAGE_SIZE - 1) // MESSAGE_SIZE
    
    # Start timing for throughput
    start_time = time.time()
    
    # Prepare all packets
    packets = []
    offset = 0
    seq_id = 0
    while offset < total_bytes:
        chunk = file_data[offset:offset + MESSAGE_SIZE]
        packets.append({
            'seq_id': seq_id,
            'data': chunk,
            'packet': create_packet(seq_id, chunk),
            'offset': offset,
            'acked': False,
            'first_send_time': None,
            'send_count': 0
        })
        seq_id += len(chunk)
        offset += len(chunk)
    
    # Sliding window variables
    window_start = 0  # first unacked packet
    next_to_send = 0  # next packet to send
    packet_delays = []
    total_packets_sent = 0
    
    # Send packets
    while window_start < len(packets):
        # Send new packets within window
        window_end = min(window_start + WINDOW_SIZE, len(packets))
        
        while next_to_send < window_end:
            pkt = packets[next_to_send]
            
            # Only send if not already acked
            if not pkt['acked']:
                try:
                    sock.sendto(pkt['packet'], (RECEIVER_IP, RECEIVER_PORT))
                    total_packets_sent += 1
                    pkt['send_count'] += 1
                    
                    # Record first send time
                    if pkt['first_send_time'] is None:
                        pkt['first_send_time'] = time.time()
                    
                    if total_packets_sent % 500 == 0:
                        progress = (window_start / len(packets)) * 100
                        print(f"Progress: {progress:.1f}% (window: {window_start}-{window_end}, sent: {total_packets_sent})", file=sys.stderr)
                        
                except Exception as e:
                    print(f"ERROR sending packet {next_to_send}: {e}", file=sys.stderr)
            
            next_to_send += 1
        
        # Receive ACKs
        ack_received = False
        retry_count = 0
        
        while retry_count < MAX_RETRIES:
            try:
                ack_packet, _ = sock.recvfrom(PACKET_SIZE)
                ack_id = parse_ack(ack_packet)
                ack_received = True
                
                # Mark all packets with seq_id < ack_id as acked
                packets_acked = 0
                for i in range(window_start, len(packets)):
                    pkt = packets[i]
                    if pkt['seq_id'] < ack_id and not pkt['acked']:
                        pkt['acked'] = True
                        packets_acked += 1
                        
                        # Calc delay for this packet
                        if pkt['first_send_time'] is not None:
                            delay = time.time() - pkt['first_send_time']
                            packet_delays.append(delay)
                
                # Slide window forward to first unacked packet
                while window_start < len(packets) and packets[window_start]['acked']:
                    window_start += 1
                
                # Reset next_to_send
                next_to_send = window_start
                
                if packets_acked > 0:
                    break  # Got useful ACK, continue sending
                    
            except socket.timeout:
                retry_count += 1
                
                # Timeout
                if retry_count % 10 == 0:
                
                # Retransmit unacked packets
                for i in range(window_start, min(window_start + WINDOW_SIZE, len(packets))):
                    pkt = packets[i]
                    if not pkt['acked']:
                        try:
                            sock.sendto(pkt['packet'], (RECEIVER_IP, RECEIVER_PORT))
                            total_packets_sent += 1
                            pkt['send_count'] += 1
                        except Exception as e:
        
        if retry_count >= MAX_RETRIES:
            sock.close()
            return None, None, None

    
    # Send empty packet to signal end
    final_seq_id = packets[-1]['seq_id'] + len(packets[-1]['data'])
    final_packet = create_packet(final_seq_id, b'')
    sock.sendto(final_packet, (RECEIVER_IP, RECEIVER_PORT))
    
    try:
        ack_packet, _ = sock.recvfrom(PACKET_SIZE)
        fin_packet, _ = sock.recvfrom(PACKET_SIZE)
    except socket.timeout:
    
    # Send FINACK
    finack_packet = create_packet(0, b'==FINACK==')
    sock.sendto(finack_packet, (RECEIVER_IP, RECEIVER_PORT))
    print("Sent FINACK - transmission complete!", file=sys.stderr)
    
    # Calc metrics
    end_time = time.time()
    total_time = end_time - start_time
    
    sock.close()
    
    # Calc results
    throughput = total_bytes / total_time
    avg_delay = sum(packet_delays) / len(packet_delays) if packet_delays else 0
    performance_metric = (0.3 * throughput / 1000) + (0.7 / avg_delay) if avg_delay > 0 else 0
    
    return throughput, avg_delay, performance_metric

def main():
    throughput, avg_delay, metric = send_file_fixed_window()
    
    if throughput is not None:
        # Output in required format (3 lines)
        print(f"{throughput:.7f}")
        print(f"{avg_delay:.7f}")
        print(f"{metric:.7f}")
    else:
        print("0.0000000")
        print("0.0000000")
        print("0.0000000")

if __name__ == "__main__":

    main()
