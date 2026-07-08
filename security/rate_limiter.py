import time
from collections import defaultdict
from threading import Lock

class RateLimiter:
    def __init__(self, max_requests=30, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = Lock()
        self.blocked_ips = defaultdict(float)
        self.block_duration = 300
        self.max_blocks_before_permanent = 5
        self.permanent_blocks = set()
        self.blocks_count = defaultdict(int)

    def is_allowed(self, ip):
        if ip in self.permanent_blocks:
            return False
        with self.lock:
            now = time.time()
            if ip in self.blocked_ips:
                if now < self.blocked_ips[ip]:
                    return False
                else:
                    del self.blocked_ips[ip]
            self.requests[ip] = [t for t in self.requests[ip] if now - t < self.window_seconds]
            if len(self.requests[ip]) >= self.max_requests:
                self.blocked_ips[ip] = now + self.block_duration
                self.blocks_count[ip] += 1
                if self.blocks_count[ip] >= self.max_blocks_before_permanent:
                    self.permanent_blocks.add(ip)
                return False
            return True

    def add_request(self, ip):
        with self.lock:
            self.requests[ip].append(time.time())
            if len(self.requests[ip]) > 1000:
                self.requests[ip] = self.requests[ip][-500:]

    def reset_ip(self, ip):
        with self.lock:
            self.requests.pop(ip, None)
            self.blocked_ips.pop(ip, None)
            self.blocks_count.pop(ip, None)
            self.permanent_blocks.discard(ip)

    def get_ip_stats(self, ip):
        with self.lock:
            now = time.time()
            recent = [t for t in self.requests.get(ip, []) if now - t < self.window_seconds]
            return {
                'request_count': len(recent),
                'is_blocked': ip in self.blocked_ips or ip in self.permanent_blocks,
                'block_expiry': self.blocked_ips.get(ip, 0),
                'is_permanently_blocked': ip in self.permanent_blocks
            }

    def clean_old_entries(self):
        with self.lock:
            now = time.time()
            for ip in list(self.requests.keys()):
                self.requests[ip] = [t for t in self.requests[ip] if now - t < self.window_seconds]
                if not self.requests[ip]:
                    del self.requests[ip]
            for ip in list(self.blocked_ips.keys()):
                if now >= self.blocked_ips[ip]:
                    del self.blocked_ips[ip]