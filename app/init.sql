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
     ('be213123-bf10-4924-9762-60a6e7cbe5c0','testing1','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',TRUE,'test1','player'),
     ('77efecb6-b780-4a61-b1d2-31e58540144c','testing2','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',FALSE,'test1','player'),
     ('254427e9-d36b-4139-ac0a-b4a2e46623e2','testing3','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',FALSE,'test1','player'),
     ('852248cd-4b4d-45ca-8d0e-7feb64b00b6f','testing4','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',FALSE,'test1','player'),
     ('21ba422f-57d6-49c8-b904-5158ce62ed95','testing5','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',TRUE,'test2','player'),
     ('ca16f0d5-6511-423e-a852-22f19c20ebe1','testing6','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',FALSE,'test2','player'),
     ('f3eb3148-0422-47fb-abcc-7340ef43640b','testing7','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',FALSE,'test2','player'),
     ('afb95225-c876-44f8-b808-084b09e2e447','testing8','$2b$12$Mbv/CLWoVwwK9H9qI3vzYOKhkcqDlFCfwjnEDHLbaj1PE99YscAVi',FALSE,'test2','player'),
     ('86dd549c-aeea-4f85-b13c-6a6d2c70b713','table','$2b$12$nsU2pRttbA7u2c5QxIvPI.ClWh.p/ZgyczpUIpzYJYyvbNm5P231K',FALSE,'minimanager','manager'),
     ('91b0e16f-5e8e-42c6-b0bf-4030981aa035','mini','$2b$12$dfIv84STkL2rXwncpXXKgeDYBUOHRV3jIc3EejIPNpo1ZbEVgIcem',FALSE,'manager','minigamemanager');

INSERT INTO accounts(user_id, balance) VALUES
 ('21ba422f-57d6-49c8-b904-5158ce62ed95',1000),
 ('ca16f0d5-6511-423e-a852-22f19c20ebe1',1000),
 ('f3eb3148-0422-47fb-abcc-7340ef43640b',2000),
 ('afb95225-c876-44f8-b808-084b09e2e447',2000),
 ('77efecb6-b780-4a61-b1d2-31e58540144c',2000),
 ('254427e9-d36b-4139-ac0a-b4a2e46623e2',2000),
 ('852248cd-4b4d-45ca-8d0e-7feb64b00b6f',2000),
 ('be213123-bf10-4924-9762-60a6e7cbe5c0',2000);

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


