# Netcode and replication
- State the authority model for each piece of state touched (server, owning client, simulated proxy) and what is replicated, when and how often.
- Check bandwidth, relevancy, ordering and join-in-progress; prefer server-validated actions over trusting the client.
- Test with a listen server plus a client, and with simulated latency and packet loss where available.
- Record what was tested and what was not (dedicated server, high latency).
