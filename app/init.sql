CREATE TABLE users(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    isleader BOOL DEFAULT FALSE,
    affiliation TEXT NOT NULL,
    access TEXT NOT NULL CHECK (access IN ('player', 'manager', 'minigamemanager'))
);

CREATE TABLE sessions(
    session_token uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    expires_at TIMESTAMP NOT NULL DEFAULT (now() + INTERVAL '8 hours'),
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
    tableId TEXT PRIMARY KEY,
    gameSelected TEXT CHECK (gameSelected IN ('Teen Patti','Poker','3 of spades','Blackjack','Rummy','Crazy 8s')),
    status TEXT CHECK (status IN ('idle','active', 'ended')),
    max_players INT
);


INSERT INTO tables (tableId, gameSelected, status, max_players) VALUES
(1,'Teen Patti','idle',6),
(2,'Poker','idle',6),
(3,'3 of spades','idle',6),
(4,'Blackjack','idle',6),
(5,'Rummy','idle',6),
(6,'Crazy 8s','idle',6);

INSERT INTO users(id,username,password_hash,isleader,affiliation,access) VALUES
     ('86dd549c-aeea-4f85-b13c-6a6d2c70b713','table','$2b$12$nsU2pRttbA7u2c5QxIvPI.ClWh.p/ZgyczpUIpzYJYyvbNm5P231K',FALSE,'minimanager','manager'),
     ('91b0e16f-5e8e-42c6-b0bf-4030981aa035','mini','$2b$12$dfIv84STkL2rXwncpXXKgeDYBUOHRV3jIc3EejIPNpo1ZbEVgIcem',FALSE,'manager','minigamemanager');

CREATE TABLE activeplayers(
    userid uuid PRIMARY KEY,
    tableid TEXT NOT NULL,
    betamount INT NOT NULL CHECK ( betamount = 350),
    timeofjoin TIMESTAMP DEFAULT now(),
    CONSTRAINT activeplayers_tableid_fkey FOREIGN KEY (tableid) REFERENCES tables(tableid),
    CONSTRAINT activeplayers_userid_fkey FOREIGN KEY (userid) REFERENCES users(id)
);

CREATE TABLE queue(
    number SERIAL PRIMARY KEY,
    tableid TEXT NOT NULL,
    userid uuid NOT NULL,
    timeofjoin TIMESTAMP DEFAULT now(),
    readytojoin BOOL NOT NULL DEFAULT FALSE,
    CONSTRAINT queue_tableid_fkey FOREIGN KEY (tableid) REFERENCES tables(tableid),
    CONSTRAINT queue_userid_fkey FOREIGN KEY (userid) REFERENCES users(id)
);

CREATE TABLE gamesplayed(
    gameid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game TEXT NOT NULL,
    tableid TEXT NOT NULL,
    timeoffinish TIMESTAMP DEFAULT now(),
    CONSTRAINT gamesplayed_tableid_fkey FOREIGN KEY (tableid) REFERENCES tables(tableid)
);

CREATE TABLE gameplayerlogs(
    id SERIAL PRIMARY KEY,
    gameid UUID NOT NULL,
    userid UUID NOT NULL,
    initialbet INT NOT NULL,
    finalamount INT NOT NULL CHECK (finalamount >= 0), 
    timeoffinish TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT gameplayerlogs_gameid_fkey FOREIGN KEY (gameid) REFERENCES gamesplayed(gameid),
    CONSTRAINT gameplayerlogs_userid_fkey FOREIGN KEY (userid) REFERENCES users(id)
);


