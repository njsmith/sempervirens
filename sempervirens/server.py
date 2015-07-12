# This file is part of sempervirens
# Copyright (C) 2015 Nathaniel Smith <njs@pobox.com>
# See file LICENSE.txt for license information.

# This file requires Python 3.4+

import sys
import time
import ssl
import ipaddress

import asyncio
from aiohttp import web
import aiodns

# XX numpy + mmap to make a scoreboard, return on GET /?
# make infrastructure to fork off processes?

# Helper for doing reverse-DNS lookups. Unnecessary on Py3.5+.
def reverse_pointer(ipaddr_string):
    ipaddr = ipaddress.ip_address(ipaddr_string)
    if sys.version_info >= (3, 5):
        return ipaddr.reverse_pointer
    else:
        if isinstance(ipaddr, ipaddress.IPv4Address):
            return (".".join(reversed(ipaddr.exploded.split(".")))
                    + ".in-addr.arpa")
        else:
            assert isinstance(ipaddr, ipaddress.IPv6Address)
            nibbles = [char for char in self.exploded if char != ":"]
            return ".".join(reversed(nibbles)) + ".ip6.arpa"

class Server(object):
    def __init__(self, host, port, *, trust_forwarded_for, ssl=None):
        self.host = host
        self.port = port
        self.trust_forwarded_for = trust_forwarded_for
        self.ssl = ssl

        self.loop = asyncio.get_event_loop()
        self.resolver = aiodns.DNSResolver(loop=self.loop)

        self.start_time = time.time()
        self.processed = 0
        self.avg_latency_sec = 0

        # URL: include some basic metadata inside the URL -- mozilla found
        # they needed to do this to allow fast sharding at high data
        # rates. maybe the instance-id and the submission-nonce? (mozilla's
        # metadata is which app, which version of it, which ping type, etc.)
        # -- https://bugzilla.mozilla.org/show_bug.cgi?id=860846 include a
        # version number of course.
        #   POST incoming.sempervirens.whereever.org/1.0/submit/<instance-id>/<submission-nonce>
        #   POST incoming.sempervirens.whereever.org/1.0/opt-out/<instance-id>

        self.app = web.Application(loop=self.loop)
        self.app.router.add("GET", "/", self.root)
        self.app.router.add("POST", "/1.0/submit/{install_id}", self.submit)
        self.app.router.add("POST", "/1.0/opt-out/{install_id}", self.opt_out)


    @asyncio.coroutine
    def start(self, host, port, ssl=None):
        # XX: create our own socket, use SO_REUSEPORT so that multiple servers
        # can all attach to the same port and the kernel will round-robin
        # between them, and then pass as sock= argument
        # len(os.sched_getaffinity(0)) is number of available CPUs
        return self.loop.create_server(self.app.make_handler(),
                                       self.host, self.port, ssl=self.ssl)

    @asyncio.coroutine
    def _rdns(self, ipaddr_string):
        # Returns a future yielding a list of domain names reverse-resolved
        # from the given ip
        rptr = reverse_pointer(ipaddr_string)
        try:
            return (yield from self.resolver.query(rptr, "PTR"))
        except aiodns.error.DNSError:
            return []

    def _request_ip(self, request):
        if self.trust_forwarded_for:
            return request.headers["x-forwarded-for"]
        else:
            (host, port) = request.transport.get_extra_info("peername")
            return host

    @asyncio.coroutine
    def root(self, request):
        # return some stats
        XX

    @asyncio.coroutine
    def submit(self, request):
        ip = self._request_ip(request)


if __name__ == "__main__":
    ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    # As of 3.4 the default context allows TLSv1, but we don't need it and
    # it's disrecommended by e.g. Mozilla. Since this makes us strictly more
    # restrictive, it's fail-safe even if Python later tightens up their
    # defaults.
    #   https://wiki.mozilla.org/Security/Server_Side_TLS
    ssl.options |= ssl.OP_NO_TLSv1
    # We could also override the cipher string if we wanted, but then we are
    # on the hook to maintain it...




# Server-side thoughts:
#   10 million requests / day = 116 requests/second
#
#   https://github.com/KeepSafe/aiohttp
#   http://blog.gmludo.eu/2015/02/macro-benchmark-with-django-flask-and-asyncio.html
#   https://github.com/saghul/aiodns

# As of May 2015, Mozilla is handling peaks of ~1.8e6 pings/hour (= ~500
# requests/second on average over that hour), with ~31 GiB data received
# during that hour. Which is. Umm. A lot. (That's ~18 KiB/ping.)
# http://ec2-50-112-66-71.us-west-2.compute.amazonaws.com:4352/#sandboxes/TelemetryChannelMetrics60DaysAggregator/outputs/TelemetryChannelMetrics60DaysAggregator.ALL.cbuf
# more stats stuff:
# http://ec2-50-112-66-71.us-west-2.compute.amazonaws.com:4352/#sandboxes
#
# Their server code:
#   https://github.com/mozilla/telemetry-server
#   https://github.com/mozilla/telemetry-server/blob/master/http/server.js
# they reject any POST without content-length, they have a max data length
# they'll accept (and if something exceeds this they respond with a 202 so it
# won't get resent), they actual pings into files that get rotated at max size
# or max time, and they log some metadata about each request (url, bytes
# written, etc.) to a separate file... the main data file is in a fixed-width
# int binary format. They spawn 1 single-threaded node.js server per CPU on a
# server.
#
# Not sure how to do storage -- would rather not just write to a single frail
# disk really. Could dump directly into cloud files? But they are not designed
# for high write rates -- each container (= "bucket") is limited to 100 object
# write requests / second, and they say "You can’t expect to write to the same
# object 20 times per second" -- http://www.rackspace.com/knowledge_center/article/best-practices-for-using-cloud-files
# s3 appears to be more scalable to high-write workloads:
#   https://docs.aws.amazon.com/AmazonS3/latest/dev/request-rate-perf-considerations.html
# Neither allow appends, though -- just creation of new objects.
# On Amazon, SimpleDB is one approach.
#    https://aws.amazon.com/simpledb/
#    -- see "Logging" section
# Postgres could also work -- they do high-throughput transaction batching (so
# one fsync for many transactions) since 9.2.
# dropping into kafka I guess does allow to tee to both disk and some realtime
# analytics aggregation
# it does sound like kafka is pretty much the tool that's designed to deal
# with this problem. but even kafka expires data based on time, not whether
# it's been processed.
#
# could batch up writes to cloud storage -- once every 30 s or whatever.
# how durable is block storage?
#   "customers are strongly encouraged to implement a RAID level 1 (mirror)
#   configuration across multiple volumes to protect against data loss in the
#   event of a storage node failure."
# so that makes sense I guess.
# we could mount 2-3 block devices in RAID-1, stream stuff out to them
# append-style, and have a thread in the background that just fsync's
# continuously, and we don't reply success until after the next fsync has
# completed.
#   $0.12/GB/month, min 75 GB
#     -> $9/mo for the cheapest block device
#
# other storage options?
# - mongodb: no. https://aphyr.com/posts/284-call-me-maybe-mongodb
# - could just forward data to 3 more http servers each of whom write it to
#   disk
#
# aggregation:
# - for each time period, number of opt-outs vs. number of opt-ins -> ratio
# - let's put opt-in period into the opt-in metadata, to make this easily
#   available for imputation without having to keep records on ever installid
# - for each project, all (TLD, installid) pairs
#   - and counts of these uniques by TLD for different time periods
# - for each
#
# I guess we'll use aiohttp, with something like:
#   16 bytes magic
# then for each record:
#   u4 + string: ip address (could be ipv6)
#   ?? u4 + string: dns name
#   u4 + string: url
#   u8: time_t
#   u4 + string: the json payload (unvalidated)
# and then roll over the log every day or so. Or for opt-outs,
#   16 bytes magic
# then for each record:
#   ?? u4 + string: ip address
#   ?? u4 + string: dns name
#   u4 + string: url
#   u8: time_t
#   u4 + string: the json payload (unvalidated)
