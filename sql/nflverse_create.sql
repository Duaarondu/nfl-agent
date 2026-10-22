CREATE LIGHTNING DATABASE NFLVERSE DESCRIBE BY "nflverse NFL data, CC-BY 4.0";

CREATE LIGHTNING FILESTORE TABLE player_stats
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/player_stats.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

CREATE LIGHTNING FILESTORE TABLE pbp
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/pbp.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

CREATE LIGHTNING FILESTORE TABLE snap_counts
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/snap_counts.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

CREATE LIGHTNING FILESTORE TABLE depth_charts
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/depth_charts.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

CREATE LIGHTNING FILESTORE TABLE injuries
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/injuries.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

CREATE LIGHTNING FILESTORE TABLE rosters
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/rosters.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

CREATE LIGHTNING FILESTORE TABLE schedules
FROM NFLVERSE
FORMAT PARQUET
OPTIONS (
  PATH "s3a://nfl-agent-data-aarondu/nflverse/schedules.parquet",
  inferSchema "true",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);
