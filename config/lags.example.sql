-- Example only. Replace device ID and ifIndex after verified inventory and LACP state.
-- Run AFTER the two interfaces have been collected into the database.
INSERT INTO lag_groups(device_id,lag_id,description)
VALUES ('GPON-LAB-01','LAG-01','Lab example 2x10G')
ON CONFLICT DO NOTHING;
INSERT INTO lag_members(device_id,lag_id,ifindex)
VALUES ('GPON-LAB-01','LAG-01',1001),('GPON-LAB-01','LAG-01',1002)
ON CONFLICT DO NOTHING;
