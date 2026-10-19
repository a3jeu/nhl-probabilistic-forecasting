-- Tables de référence : saisons et équipes
-- Sources : api.nhle.com/stats/rest/en/season et /team.

CREATE TABLE IF NOT EXISTS `seasons` (
  `season_id` varchar(10) NOT NULL,
  `year_start` int DEFAULT NULL,
  `date_start` date DEFAULT NULL,
  `date_end` date DEFAULT NULL,
  `date_start_pre` date DEFAULT NULL,
  `date_end_post` date DEFAULT NULL,
  `nb_games` int DEFAULT NULL,
  `desc` varchar(255) DEFAULT NULL,
  `prev_season_id` varchar(10) DEFAULT NULL,
  `league` varchar(10) NOT NULL DEFAULT 'NHL',
  PRIMARY KEY (`season_id`,`league`),
  KEY `index2` (`season_id`,`date_start`,`league`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `teams` (
  `team_id` int NOT NULL COMMENT 'NHL reference',
  `team_name` varchar(45) DEFAULT NULL,
  `prev_team_id` int DEFAULT NULL,
  `abbreviation` varchar(5) DEFAULT NULL,
  `abbreviation_nhl` varchar(3) DEFAULT NULL,
  `first_season` varchar(45) DEFAULT NULL,
  `league` varchar(45) NOT NULL DEFAULT 'nhl',
  `active` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`team_id`,`league`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
