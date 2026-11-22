CREATE TABLE IF NOT EXISTS devices (
 id TEXT PRIMARY KEY, vendor TEXT NOT NULL, technology TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interfaces (
 device_id TEXT NOT NULL REFERENCES devices(id), ifindex BIGINT NOT NULL,
 name TEXT NOT NULL, capacity_bps BIGINT NOT NULL,
 PRIMARY KEY(device_id,ifindex)
);
CREATE TABLE IF NOT EXISTS metrics (
 id BIGSERIAL PRIMARY KEY, device_id TEXT NOT NULL, ifindex BIGINT NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL, rx_bps DOUBLE PRECISION NOT NULL,
 tx_bps DOUBLE PRECISION NOT NULL, utilization_percent DOUBLE PRECISION NOT NULL,
 source TEXT NOT NULL, FOREIGN KEY(device_id,ifindex) REFERENCES interfaces(device_id,ifindex)
);
CREATE INDEX IF NOT EXISTS metrics_latest ON metrics(device_id,ifindex,observed_at DESC);
CREATE TABLE IF NOT EXISTS alerts (
 id BIGSERIAL PRIMARY KEY, device_id TEXT NOT NULL, ifindex BIGINT NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL, utilization_percent DOUBLE PRECISION NOT NULL,
 message TEXT NOT NULL
);
