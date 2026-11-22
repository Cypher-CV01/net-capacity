-- v0.2: explicit LAG membership; never infer members from port names.
CREATE TABLE IF NOT EXISTS lag_groups (
  device_id TEXT NOT NULL REFERENCES devices(id),
  lag_id TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (device_id, lag_id)
);
CREATE TABLE IF NOT EXISTS lag_members (
  device_id TEXT NOT NULL,
  lag_id TEXT NOT NULL,
  ifindex BIGINT NOT NULL,
  PRIMARY KEY(device_id, lag_id, ifindex),
  FOREIGN KEY(device_id,lag_id) REFERENCES lag_groups(device_id,lag_id) ON DELETE CASCADE,
  FOREIGN KEY(device_id,ifindex) REFERENCES interfaces(device_id,ifindex)
);
