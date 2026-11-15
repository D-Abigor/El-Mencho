# El-Mencho

> **Status: Archived**  
> This repository is an archive of the backend and transaction system built for the MLSC Casino Event (2026). It is kept here as a reference for the project.

Backend system built for an in-person, casino-themed event organized by the MLSC student society. It handled player accounts, virtual chip balances, game tables, and live peer-to-peer transfers.

## Background

During the event, participants played games like Poker, Blackjack, and Teen Patti using virtual chips.

The main challenge was making sure balances stayed accurate under live use as well as designing and implementing a queue system for each table. 

Now that the event is over, this repository is preserved as an archive of that codebase.

## Architecture

```
                  ┌──────────────┐
   HTTPS ──▶     │    NGINX     │     Reverse proxy
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │   FastAPI    │     Application server
                  │  (Uvicorn)   │
                  └──────┬───────┘
                         │  Connection pool
                  ┌──────▼───────┐
                  │  PostgreSQL  │     Database
                  │    (Docker)  │
                  └──────────────┘
```

- **FastAPI** handles routing and background session cleanup
- **asyncpg** connects directly to PostgreSQL without an ORM for fast queries
- **PostgreSQL 16** runs in Docker with a healthcheck so the app waits for the database to be ready before starting

## Database Schema

| Table | Purpose |
|---|---|
| `users` | User accounts, hashed passwords, roles (`player`, `manager`, `minigamemanager`), and team affiliation |
| `sessions` | Active login sessions, automatically cleaned up after expiry |
| `accounts` | Chip balances with a database check ensuring balances never drop below zero |
| `transactions` | Log of all completed transfers between users |
| `tables` | Status and settings for game tables (Poker, Blackjack, Teen Patti, etc.) |
| `activeplayers` | Players currently seated at a table |
| `queue` | Line of players waiting to join a table |
| `gamesplayed` | Record of finished games |
| `gameplayerlogs` | Final payouts and results per player |

## Handling Concurrent Transfers

When two users transfer chips to each other at the same time, naive locking can cause a deadlock (User A waits for User B, while User B waits for User A). 

To prevent this, the transfer function sorts the two account IDs before locking their rows:

```python
ids = sorted([source_uuid, dest_uuid], key=lambda u: str(u))
await conn.fetchrow("SELECT balance FROM accounts WHERE user_id = $1 FOR UPDATE;", ids[0])
await conn.fetchrow("SELECT balance FROM accounts WHERE user_id = $1 FOR UPDATE;", ids[1])
```

By always locking accounts in a consistent order, neither transaction can block the other in a circular wait. Both balance updates (deduction and addition) and the transaction log are wrapped together so that if any step fails, nothing changes.

## API Overview

### Public
| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Landing page |
| `GET` | `/login` | Login page |
| `GET` | `/leaderBoard` | Leaderboard |
| `POST` | `/login` | Authenticate and create session |

### Player
| Method | Path | Description |
|---|---|---|
| `GET` | `/home` | Dashboard showing current balance and history |
| `POST` | `/transfer` | Send chips to another player |
| `POST` | `/queue` | Join a table queue |
| `GET` | `/play` | Current game screen |

### Manager
| Method | Path | Description |
|---|---|---|
| `GET` | `/tables` | View all tables |
| `POST` | `/table/{id}/configure` | Set game type and max players |
| `POST` | `/table/{id}/start` | Open a table |
| `POST` | `/table/{id}/end` | Submit game results and issue payouts |

## Security & Checks

- Passwords hashed using `bcrypt` (work factor 12)
- Server-side session tokens with automatic expiration
- Database-level constraint (`balance >= 0`) as a safeguard against negative balances
- Custom exception handling for expired sessions, invalid transfers, and database errors

## Deployment (Event Setup)

For the live event, the system was hosted on a DigitalOcean droplet:

- **NGINX:** Installed on the host as a reverse proxy, listening on ports 80/443 to handle TLS termination and forward requests internally to the app on port 31000.
- **TLS Configuration:** SSL certificates configured directly in NGINX so players could securely access the platform over HTTPS from their phones.
- **Docker Compose:** Ran the FastAPI app and PostgreSQL database containers together on the droplet, keeping database storage persisted in a host volume.

## Running Locally

```bash
docker compose up --build
```

The application runs on `http://localhost:31000`, with PostgreSQL on `localhost:5432`.

## Tech Stack

- Python (FastAPI, asyncpg)
- PostgreSQL
- Docker Compose
- NGINX
