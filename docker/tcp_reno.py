#!/usr/bin/env python3
"""
TCP Reno Protocol Implementation - WITH DETAILED DEBUG OUTPUT
ECS 152A - Computer Networks Project 1 - Extra Credit
"""

import socket
import time
import threading
import sys

# Constants
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
RECEIVER_IP = '127.0.0.1'
RECEIVER_PORT = 5001
TIMEOUT = 0.5
INITIAL_CWND = 1
INITIAL_SSTHRESH = 64
FILE_PATH = 'file.mp3'

def create_packet(seq_id, data):
    seq_bytes = int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big')
    return seq_bytes + data

def parse_ack(ack_packet):
    if len(ack_packet) >= SEQ_ID_SIZE:
        ack_id = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
        return ack_id
    return -1

class TCPRenoSender:
    def __init__(self, file_data, sock):
        self.file_data = file_data
        self.sock = sock
        self.total_bytes = len(file_data)
        
        self.window_base = 0
        self.next_seq = 0
        
        self.cwnd = INITIAL_CWND
        self.ssthresh = INITIAL_SSTHRESH
        self.state = "SLOW_START"
        
        self.last_ack = 0
        self.dup_ack_count = 0
        
        self.packets = {}
        self.acked = set()
        
        self.packet_delays = []
        self.start_time = None
        
        self.lock = threading.Lock()
        self.running = True
        
        # Stats for printing
        self.packets_sent_count = 0
        self.retransmissions = 0
        self.timeouts = 0
        self.fast_retransmits = 0
        
    def get_window_size_bytes(self):
        return int(self.cwnd * MESSAGE_SIZE)
    
    def print_state(self, event):
        """Print current congestion control state."""
        progress = (self.window_base / self.total_bytes) * 100 if self.total_bytes > 0 else 0
        print(f"[{event}] State: {self.state}, cwnd: {self.cwnd:.2f} pkts, ssthresh: {self.ssthresh:.2f} pkts, "
              f"progress: {progress:.1f}%, window_base: {self.window_base}, next_seq: {self.next_seq}", 
              file=sys.stderr)
    
    def on_new_ack(self):
        old_state = self.state
        old_cwnd = self.cwnd
        
        if self.state == "SLOW_START":
            self.cwnd += 1
            if self.cwnd >= self.ssthresh:
                self.state = "CONGESTION_AVOIDANCE"
                print(f"[STATE CHANGE] SLOW_START -> CONGESTION_AVOIDANCE (cwnd={self.cwnd:.2f})", file=sys.stderr)
        elif self.state == "CONGESTION_AVOIDANCE":
            self.cwnd += 1.0 / self.cwnd
        elif self.state == "FAST_RECOVERY":
            self.cwnd = self.ssthresh
            self.state = "CONGESTION_AVOIDANCE"
            print(f"[STATE CHANGE] FAST_RECOVERY -> CONGESTION_AVOIDANCE (cwnd={self.cwnd:.2f})", file=sys.stderr)
    
    def on_timeout(self):
        print(f"[TIMEOUT] Reducing cwnd from {self.cwnd:.2f} to 1, ssthresh to {max(self.cwnd / 2, 2):.2f}", file=sys.stderr)
        self.timeouts += 1
        self.ssthresh = max(self.cwnd / 2, 2)
        self.cwnd = INITIAL_CWND
        self.state = "SLOW_START"
        self.dup_ack_count = 0
    
    def on_triple_dup_ack(self, ack_id):
        print(f"[FAST RETRANSMIT] Triple dup ACK for seq {ack_id}, retransmitting...", file=sys.stderr)
        self.fast_retransmits += 1
        
        if ack_id in self.packets:
            chunk, _, first_send_time = self.packets[ack_id]
            packet = create_packet(ack_id, chunk)
            self.sock.sendto(packet, (RECEIVER_IP, RECEIVER_PORT))
            self.retransmissions += 1
            current_time = time.time()
            self.packets[ack_id] = (chunk, current_time, first_send_time)
        
        old_cwnd = self.cwnd
        self.ssthresh = max(self.cwnd / 2, 2)
        self.cwnd = self.ssthresh + 3
        self.state = "FAST_RECOVERY"
        print(f"[FAST RECOVERY] cwnd: {old_cwnd:.2f} -> {self.cwnd:.2f}, ssthresh: {self.ssthresh:.2f}", file=sys.stderr)
    
    def send_packets(self):
        print(f"[SEND] Starting to send {self.total_bytes} bytes ({self.total_bytes // MESSAGE_SIZE + 1} packets)", file=sys.stderr)
        last_print = 0
        
        while self.next_seq < self.total_bytes:
            with self.lock:
                bytes_in_flight = self.next_seq - self.window_base
                window_size_bytes = self.get_window_size_bytes()
                
                if bytes_in_flight >= window_size_bytes:
                    time.sleep(0.001)
                    continue
                
                offset = self.next_seq
                chunk = self.file_data[offset:offset + MESSAGE_SIZE]
                if not chunk:
                    break
                
                packet = create_packet(self.next_seq, chunk)
                self.sock.sendto(packet, (RECEIVER_IP, RECEIVER_PORT))
                
                self.packets_sent_count += 1
                current_time = time.time()
                self.packets[self.next_seq] = (chunk, current_time, current_time)
                
                # Print progress every 100 packets
                if self.packets_sent_count % 100 == 0:
                    progress = (self.next_seq / self.total_bytes) * 100
                    print(f"[SEND] Sent {self.packets_sent_count} packets, {progress:.1f}% complete, "
                          f"cwnd={self.cwnd:.2f}, in_flight={len(self.packets)} pkts", file=sys.stderr)
                
                self.next_seq += len(chunk)
        
        print(f"[SEND] All packets queued for sending (sent {self.packets_sent_count} total)", file=sys.stderr)
    
    def receive_acks(self):
        self.sock.settimeout(0.05)
        acks_received = 0
        last_ack_print = 0
        
        while self.running:
            try:
                ack_packet, _ = self.sock.recvfrom(PACKET_SIZE)
                ack_id = parse_ack(ack_packet)
                acks_received += 1
                
                with self.lock:
                    if ack_id == self.last_ack:
                        self.dup_ack_count += 1
                        
                        if self.dup_ack_count == 3:
                            self.on_triple_dup_ack(ack_id)
                        elif self.state == "FAST_RECOVERY":
                            self.cwnd += 1
                    else:
                        if ack_id > self.last_ack:
                            acked_packets = []
                            for seq_id in list(self.packets.keys()):
                                if seq_id < ack_id:
                                    if seq_id not in self.acked:
                                        chunk, _, first_send_time = self.packets[seq_id]
                                        delay = time.time() - first_send_time
                                        self.packet_delays.append(delay)
                                        self.acked.add(seq_id)
                                        acked_packets.append(seq_id)
                            
                            self.on_new_ack()
                            self.window_base = ack_id
                            
                            for seq_id in acked_packets:
                                if seq_id in self.packets:
                                    del self.packets[seq_id]
                            
                            self.last_ack = ack_id
                            self.dup_ack_count = 0
                            
                            # Print progress every 100 ACKs
                            if acks_received - last_ack_print >= 100:
                                progress = (self.window_base / self.total_bytes) * 100
                                print(f"[ACK] Received {acks_received} ACKs, {progress:.1f}% acknowledged, "
                                      f"cwnd={self.cwnd:.2f}, outstanding={len(self.packets)} pkts", file=sys.stderr)
                                last_ack_print = acks_received
                    
            except socket.timeout:
                with self.lock:
                    current_time = time.time()
                    timeout_occurred = False
                    
                    for seq_id, (chunk, send_time, first_send_time) in list(self.packets.items()):
                        if seq_id not in self.acked and (current_time - send_time) > TIMEOUT:
                            print(f"[RETRANSMIT] Timeout for packet seq={seq_id}", file=sys.stderr)
                            packet = create_packet(seq_id, chunk)
                            self.sock.sendto(packet, (RECEIVER_IP, RECEIVER_PORT))
                            self.retransmissions += 1
                            self.packets[seq_id] = (chunk, current_time, first_send_time)
                            
                            if not timeout_occurred:
                                self.on_timeout()
                                timeout_occurred = True
            except Exception as e:
                pass
    
    def send_file(self):
        print("\n" + "="*60, file=sys.stderr)
        print("TCP RENO TRANSMISSION STARTING", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print(f"File size: {self.total_bytes} bytes ({self.total_bytes/1024/1024:.2f} MB)", file=sys.stderr)
        print(f"Initial cwnd: {self.cwnd} packets", file=sys.stderr)
        print(f"Initial ssthresh: {self.ssthresh} packets", file=sys.stderr)
        print(f"Timeout: {TIMEOUT}s", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        
        self.start_time = time.time()
        
        receiver_thread = threading.Thread(target=self.receive_acks)
        receiver_thread.daemon = True
        receiver_thread.start()
        
        self.send_packets()
        
        print(f"\n[WAIT] Waiting for all ACKs (window_base={self.window_base}/{self.total_bytes})...", file=sys.stderr)
        max_wait = 30
        wait_start = time.time()
        while self.window_base < self.total_bytes:
            if time.time() - wait_start > max_wait:
                print("[WARN] Timeout waiting for final ACKs", file=sys.stderr)
                break
            time.sleep(0.1)
        
        print(f"[FINALIZE] Sending final packet and FINACK...", file=sys.stderr)
        final_packet = create_packet(self.window_base, b'')
        for _ in range(5):
            self.sock.sendto(final_packet, (RECEIVER_IP, RECEIVER_PORT))
            time.sleep(0.05)
        
        self.sock.settimeout(1.0)
        try:
            ack_packet, _ = self.sock.recvfrom(PACKET_SIZE)
            fin_packet, _ = self.sock.recvfrom(PACKET_SIZE)
            print("[FINALIZE] Received ACK and FIN", file=sys.stderr)
        except socket.timeout:
            print("[FINALIZE] Timeout waiting for FIN", file=sys.stderr)
        
        finack_packet = create_packet(0, b'==FINACK==')
        self.sock.sendto(finack_packet, (RECEIVER_IP, RECEIVER_PORT))
        print("[FINALIZE] Sent FINACK", file=sys.stderr)
        
        self.running = False
        
        end_time = time.time()
        total_time = end_time - self.start_time
        
        throughput = self.total_bytes / total_time if total_time > 0 else 0
        avg_delay = sum(self.packet_delays) / len(self.packet_delays) if self.packet_delays else 0
        performance_metric = (0.3 * throughput / 1000) + (0.7 / avg_delay) if avg_delay > 0 else 0
        
        print("\n" + "="*60, file=sys.stderr)
        print("TRANSMISSION COMPLETE", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print(f"Total time: {total_time:.2f} seconds", file=sys.stderr)
        print(f"Packets sent: {self.packets_sent_count}", file=sys.stderr)
        print(f"Retransmissions: {self.retransmissions}", file=sys.stderr)
        print(f"Timeouts: {self.timeouts}", file=sys.stderr)
        print(f"Fast retransmits: {self.fast_retransmits}", file=sys.stderr)
        print(f"Throughput: {throughput:.2f} bytes/sec ({throughput/1024:.2f} KB/sec)", file=sys.stderr)
        print(f"Average delay: {avg_delay:.6f} seconds", file=sys.stderr)
        print(f"Performance metric: {performance_metric:.6f}", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        
        return throughput, avg_delay, performance_metric

def send_file_tcp_reno():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    with open(FILE_PATH, 'rb') as f:
        file_data = f.read()
    
    sender = TCPRenoSender(file_data, sock)
    throughput, avg_delay, performance_metric = sender.send_file()
    
    sock.close()
    
    return throughput, avg_delay, performance_metric

def main():
    throughput, avg_delay, metric = send_file_tcp_reno()
    
    if throughput is not None and throughput > 0:
        print(f"{throughput:.7f}")
        print(f"{avg_delay:.7f}")
        print(f"{metric:.7f}")
    else:
        print("0.0000000")
        print("0.0000000")
        print("0.0000000")

if __name__ == "__main__":
    main()