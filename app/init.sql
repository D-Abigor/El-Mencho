CREATE TABLE users(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    isleader BOOL DEFAULT FALSE,
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

CREATE TABLE tables(                                        -- FIX: added semicolons throughout
    tableid INT PRIMARY KEY,
    gameselected TEXT CHECK (gameselected IN ('teenPatti','poker','spadesOf3','blackjack','rummy','crazy8s','')),
    status TEXT CHECK (status IN ('waiting','active')),
    max_players INT
);

INSERT INTO tables(tableid, gameselected, status, max_players) VALUES  -- FIX: single quotes
    (1, '', 'waiting', 6),
    (2, '', 'waiting', 6),
    (3, '', 'waiting', 6),
    (4, '', 'waiting', 6),
    (5, '', 'waiting', 6),
    (6, '', 'waiting', 6);

CREATE TABLE activeplayers(
    userid uuid PRIMARY KEY,
    tableid INT NOT NULL,
    betamount INT NOT NULL,
    timeofjoin TIMESTAMP DEFAULT now(),
    CONSTRAINT activeplayers_tableid_fkey FOREIGN KEY (tableid) REFERENCES tables(tableid),
    CONSTRAINT activeplayers_userid_fkey FOREIGN KEY (userid) REFERENCES users(id)
);

CREATE TABLE queue(
    number SERIAL PRIMARY KEY,
    tableid INT NOT NULL,
    userid uuid NOT NULL,
    timeofjoin TIMESTAMP DEFAULT now(),
    readytojoin BOOL NOT NULL DEFAULT FALSE,
    CONSTRAINT queue_tableid_fkey FOREIGN KEY (tableid) REFERENCES tables(tableid),
    CONSTRAINT queue_userid_fkey FOREIGN KEY (userid) REFERENCES users(id)
);

CREATE TABLE gamesplayed(
    gameid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game TEXT NOT NULL,
    tableid INT NOT NULL,
    timeoffinish TIMESTAMP DEFAULT now(),
    CONSTRAINT gamesplayed_tableid_fkey FOREIGN KEY (tableid) REFERENCES tables(tableid)  -- FIX: syntax
);

CREATE TABLE gameplayerlogs(
    id SERIAL PRIMARY KEY,
    gameid UUID NOT NULL,
    userid UUID NOT NULL,
    initialbet INT NOT NULL,
    finalamount INT NOT NULL CHECK (finalamount >= 0),       -- FIX: column name was inconsistent
    timeoffinish TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT gameplayerlogs_gameid_fkey FOREIGN KEY (gameid) REFERENCES gamesplayed(gameid),
    CONSTRAINT gameplayerlogs_userid_fkey FOREIGN KEY (userid) REFERENCES users(id)
    -- FIX: removed bogus FK on timeoffinish — timestamps can't reference another table
);
