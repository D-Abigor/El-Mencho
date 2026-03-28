CREATE TABLE users(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text UNIQUE NOT NULL,
    password_hash text NOT NULL,
    isLeader BOOL DEFAULT FALSE,
    affiliation TEXT NOT NULL,
    access text NOT NULL CHECK ( access IN ('player', 'manager'))
);

CREATE TABLE sessions(
    session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    expires_at TIMESTAMP NOT NULL DEFAULT (now() + INTERVAL '5 hours'),
    CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE accounts(
    user_id uuid PRIMARY KEY,
    balance INTEGER CHECK ( balance>=0),
    CONSTRAINT user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
 );

CREATE TABLE transactions(
    transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change INTEGER NOT NULL,
    source uuid REFERENCES users(id) NOT NULL,
    destination uuid REFERENCES users(id) NOT NULL,
    processed_at TIMESTAMP DEFAULT now()
 );



CREATE TABLE gamesPlayed(
  gameId UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  game TEXT NOT NULL,
  timeOfFinish TIMESTAMP DEFAULT now(),
  winner UUID NOT NULL,
  CONSTRAINT winner_fkey FOREIGN KEY REFERENCES users(id)
);

CREATE TABLE activeGames(
  user_id uuid PRIMARY KEY,
  bet_amount INTEGER NOT NULL CHECK ( bet_amount >= /////// ),
  game TEXT NOT NULL,
  CONSTRAINT user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
);


CREATE TABLE gamePlayers(
  ID SERIAL PRIMARY KEY, 
  gameId UUID NOT NULL,
  user_id UUID NOT NULL,
  initial_bet INT NOT NULL,
  final_amount INT NOT NULL CHECK ( final_amount >= 0),
  timeOfFinish TIMESTAMP NOT NULL DEFAULT now(),
  CONSTRAINT gameId_fkey FOREIGN KEY (gameId) REFERENCES gamesPlayed(gameId),
  CONSTRAINT user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT finishTime_fkey FOREIGN KEY (timeOfFinish) REFERENCES gamesPlayed(timeOfFinish),
);




CREATE TABLE queue(
  number SERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  game TEXT NOT NULL,
  timeOfJoin TIMESTAMP DEFAULT now(),
  CONSTRAINT user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
);
