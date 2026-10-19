-- Matchs et alignements
-- Sources : api.nhle.com/stats/rest/en/game et api-web.nhle.com/v1/gamecenter/{id}/boxscore.

CREATE TABLE IF NOT EXISTS `games` (
  `game_id` varchar(45) NOT NULL,
  `season_id` varchar(45) DEFAULT NULL,
  `game_type` varchar(45) DEFAULT NULL COMMENT 'PR/R/P',
  `status` varchar(45) DEFAULT NULL,
  `date` date DEFAULT NULL,
  `time` varchar(45) DEFAULT NULL,
  `home` int DEFAULT NULL,
  `away` int DEFAULT NULL,
  `score_home` int DEFAULT NULL,
  `score_away` int DEFAULT NULL,
  `end_game_type` varchar(45) DEFAULT NULL,
  `period` varchar(45) DEFAULT NULL,
  `clock` varchar(45) DEFAULT NULL,
  `league` varchar(45) NOT NULL DEFAULT 'nhl',
  PRIMARY KEY (`game_id`,`league`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `rosters` (
  `roster_id` int NOT NULL AUTO_INCREMENT,
  `season_id` int DEFAULT NULL,
  `game_id` int DEFAULT NULL,
  `team_id` int DEFAULT NULL,
  `player_id` int DEFAULT NULL,
  `position` varchar(5) DEFAULT NULL COMMENT 'p/g',
  `position_long` varchar(45) DEFAULT NULL,
  `scratched` tinyint DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `imported_from` varchar(45) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`roster_id`),
  UNIQUE KEY `player_id` (`game_id`,`player_id`),
  KEY `index4` (`season_id`,`game_id`,`scratched`,`position`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
