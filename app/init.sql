CREATE TABLE users(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text UNIQUE NOT NULL,
    password_hash text NOT NULL,
    isLeader BOOLEAN DEFAULT FALSE,
    affiliation TEXT NOT NULL,
    access TEXT NOT NULL CHECK (access IN ('player', 'manager'))
);

CREATE TABLE sessions(
    session_token uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    expires_at TIMESTAMP NOT NULL DEFAULT (now() + INTERVAL '5 hours'),
    CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE accounts(
    user_id uuid PRIMARY KEY,
    balance INTEGER CHECK (balance >= 0),
    CONSTRAINT user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE transactions(
    transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change INTEGER NOT NULL,
    source uuid NOT NULL REFERENCES users(id),
    destination uuid NOT NULL REFERENCES users(id),
    processed_at TIMESTAMP DEFAULT now()
);

CREATE TABLE tables(
    tableId INT PRIMARY KEY,
    gameSelected TEXT CHECK (gameSelected IN ('Teen Patti','Poker','3 of spades','Blackjack','Rummy','Crazy 8s')),
    status TEXT CHECK (status IN ('idle', 'ready','running', 'ended')),
    max_players INT
);

-- inserting pre-baked tables
INSERT INTO tables (tableId, gameSelected, status, max_players) VALUES
(1,'Teen Patti','idle',6),
(2,'Poker','idle',6),
(3,'3 of spades','idle',6),
(4,'Blackjack','idle',6),
(5,'Rummy','idle',6),
(6,'Crazy 8s','idle',6);

CREATE TABLE activePlayers(
    userId uuid PRIMARY KEY,
    tableId INT NOT NULL,
    betAmount INT NOT NULL,
    timeOfJoin TIMESTAMP DEFAULT now(),
    CONSTRAINT activePlayers_tableId_fkey FOREIGN KEY (tableId) REFERENCES tables(tableId),
    CONSTRAINT activePlayers_userId_fkey FOREIGN KEY (userId) REFERENCES users(id)
);

CREATE TABLE queue(
    number SERIAL PRIMARY KEY,
    tableId INT NOT NULL,
    userId uuid NOT NULL,
    timeOfJoin TIMESTAMP DEFAULT now(),
    readyToJoin BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT queue_tableId_fkey FOREIGN KEY (tableId) REFERENCES tables(tableId),
    CONSTRAINT queue_userId_fkey FOREIGN KEY (userId) REFERENCES users(id)
);

CREATE TABLE gamesPlayed(
    gameId UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game TEXT NOT NULL,
    tableId INT NOT NULL,
    timeOfFinish TIMESTAMP DEFAULT now(),
    CONSTRAINT gamesPlayed_tableId_fkey FOREIGN KEY (tableId) REFERENCES tables(tableId)
);

CREATE TABLE gamePlayerLogs(
    id SERIAL PRIMARY KEY, 
    gameId UUID NOT NULL,
    userId UUID NOT NULL,
    initialBet INT NOT NULL,
    finalAmount INT NOT NULL CHECK (finalAmount >= 0),
    timeOfFinish TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT gamePlayerLogs_gameId_fkey FOREIGN KEY (gameId) REFERENCES gamesPlayed(gameId),
    CONSTRAINT gamePlayerLogs_userId_fkey FOREIGN KEY (userId) REFERENCES users(id)
);
