import socket
import threading
import random
import time
import queue
import sys
import json
import multiprocessing

# load config file
config = json.load(open('config/config.json'))

# set params
host = config['host']
port1 = config['port1']
port2 = config['port2']
port3 = config['port3']
run_duration = config['run_duration']
max_internal = config['max_internal']
max_clock_speed = config['max_clock_speed']

class VirtualMachine:
    def __init__(self, machine_id, port, peers):
        '''
        Class that runs a virtual machine that can send and receive messages.
        Sets clock speed at initialization and logs info.

        Parameters:
        ----------
        machine_id : int
            The unique identifier for this machine.
        port : int
            The port number to listen on for incoming connections.
        peers : list of tuples
            Each tuple contains (peer_id, host, port) for each peer.
        '''
        self.machine_id = machine_id
        self.port = port
        self.peers = peers

        # this will map peer_id to a socket object
        self.peer_sockets = {}

        # get random clock
        self.clock_speed = random.randint(1, max_clock_speed)

        # initialize clock and queue
        self.logical_clock = 0
        self.inbound_queue = queue.Queue()

        # create log file
        self.log_file = f"logs/machine_{self.machine_id}_log.txt"
        with open(self.log_file, "w") as f:
            f.write(f"Max internal event={max_internal}\n")
            f.write(f"Max clock speed={max_clock_speed}\n")
            f.write(f"Machine {self.machine_id} initialized. Clock rate={self.clock_speed}\n")

        # set up socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # allow it so we can use the same address multiple times
        # since all machines are on the same host
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.socket.bind((host, self.port))
        self.socket.listen(5)

        # set up thread to listen from peers
        self.connection_thread = threading.Thread(target=self.setup_connection, daemon=True)
        self.connection_thread.start()

    def setup_connection(self):
        '''
        Continuously listens for incoming connections.
        Accepts new connections and starts a new thread to listen for responses.
        '''
        while True:
            conn, _ = self.socket.accept()
            threading.Thread(target=self.handle_requests, args=(conn,), daemon=True).start()

    def handle_requests(self, conn):
        '''
        Handles incoming requests from peers.
        '''
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    # if no data, break since connection is closed
                    break
                # decode data and strip any whitespace, no protocol
                # message in form sender_id:clock_value
                message_str = data.decode('utf-8').strip()
                if message_str:
                    parts = message_str.split(":")
                    sender_id = int(parts[0])
                    sender_clock = int(parts[1])
                    # add in inbound queue
                    self.inbound_queue.put((sender_id, sender_clock))
            except ConnectionResetError:
                break
            except Exception as e:
                print(f"[Machine {self.machine_id}] handle request error: {e}", file=sys.stderr)
                break

        conn.close()

    def connect_to_peers(self):
        '''
        Creates and saves socket connections to all peers.
        '''
        for (peer_id, host, port) in self.peers:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connected = False
            while not connected:
                try:
                    s.connect((host, port))
                    connected = True
                except ConnectionRefusedError:
                    time.sleep(0.1)  # wait and try again
            self.peer_sockets[peer_id] = s

    def _log_event(self, event_type, extra_info=""):
        """
        Appends an event line to the machine's log file.
        event_type: e.g. "RECEIVE", "SEND", "INTERNAL"
        extra_info: any extra detail to record
        """
        system_time = time.time()
        log_line = (f"[{event_type}] SystemTime={system_time:.4f}, "
                    f"LogicalClock={self.logical_clock}, "
                    f"Info={extra_info}\n")
        with open(self.log_file, "a") as f:
            f.write(log_line)

    def update_logical_clock_on_receive(self, sender_clock):
        """
        Update local logical clock when receiving a message:
          local_clock = max(local_clock, sender_clock) + 1
        """
        self.logical_clock = max(self.logical_clock, sender_clock) + 1

    def increment_clock(self):
        """
        For send or internal events, we just do: local_clock += 1
        """
        self.logical_clock += 1

    def send_message(self, peer_id):
        """
        Sends a message of the form "my_id:my_logical_clock" to one peer.
        """
        if peer_id not in self.peer_sockets:
            # socket doesn't exist, shouldn't happen
            return
        msg = f"{self.machine_id}:{self.logical_clock}\n".encode('utf-8')
        try:
            self.peer_sockets[peer_id].sendall(msg)
        except OSError as e:
            print(f"[Machine {self.machine_id}] Failed to send to {peer_id}: {e}", file=sys.stderr)

    def main_loop(self, force_test=None):
        """
        This simulates the “instruction cycles” for the machine. On each clock cycle:
          - If inbound queue not empty: process one message
          - Else: randomly decide to send or do an internal event
        We run indefinitely; you could add a termination condition if needed.

        Parameters:
        ----------
        force_test : int
            If an int is provided, it runs the main loop once for that integer then exits.
            ONLY USED FOR UNIT TESTING
        """
        while True:
            sleep_time = 1.0 / self.clock_speed

            # check inbound queue
            if not self.inbound_queue.empty():
                sender_id, sender_clock = self.inbound_queue.get()
                old_clock = self.logical_clock
                # update logical clock based on msg
                self.update_logical_clock_on_receive(sender_clock)
                queue_size = self.inbound_queue.qsize()
                # log msg info
                self._log_event(
                    event_type="RECEIVE",
                    extra_info=(f"From={sender_id}, SenderClock={sender_clock}, "
                                f"QueueSizeAfter={queue_size}, OldLocalClock={old_clock}")
                )
            else:
                # if nothing in inbound queue, random action
                choice = random.randint(1, max_internal)
                if force_test:
                    choice = force_test
                if choice == 1:
                    # send to first peer in dictionary
                    if self.peer_sockets:
                        peer_id = list(self.peer_sockets.keys())[0]
                        self.send_message(peer_id)
                        self.increment_clock()
                        self._log_event("SEND", f"To={peer_id}")
                elif choice == 2:
                    # send to the other peer (i.e., second peer in dict)
                    if len(self.peer_sockets) > 1:
                        peer_id = list(self.peer_sockets.keys())[1]
                        self.send_message(peer_id)
                        self.increment_clock()
                        self._log_event("SEND", f"To={peer_id}")
                    else:
                        # error handling
                        # fallback to internal event if there's only 1 peer connected
                        self.increment_clock()
                        self._log_event("INTERNAL", "Random=2 but only one peer.")
                elif choice == 3:
                    # send to both peers
                    for peer_id in self.peer_sockets:
                        self.send_message(peer_id)
                    self.increment_clock()
                    self._log_event("SEND", f"Broadcast to peers {list(self.peer_sockets.keys())}")
                else:
                    # treat cycle as internal event
                    old_clock = self.logical_clock
                    self.increment_clock()
                    self._log_event("INTERNAL", f"old_clock={old_clock}")

            # sleep for a "tick"
            if force_test:
                break
            time.sleep(sleep_time)

# each vm needs to be initialized in own process
def start_virtual_machine(machine_id, port, peers):
    vm = VirtualMachine(machine_id, port, peers)

    # allow time for others to be initialized
    time.sleep(0.5)

    vm.connect_to_peers()
    vm.main_loop()

def main():
    ports = [port1, port2, port3]
    processes = []

    # create VirtualMachine objects w/ others as peers
    for i in range(3):
        machine_id = i + 1
        listen_port = ports[i]
        # put together peer info
        # (id, host, port)
        peer_info = []
        for j in range(3):
            # make sure we don't add ourselves
            if j != i:
                peer_info.append((j+1, host, ports[j]))
        # start process
        p = multiprocessing.Process(target=start_virtual_machine, args=(machine_id, listen_port, peer_info))
        p.start()
        processes.append(p)

    print(f"System running for {run_duration} seconds...")
    time.sleep(run_duration)
    print("Done.")

    # terminate all processes
    for p in processes:
        p.terminate()

if __name__ == "__main__":
    main()