-- Run this once on the OpenDental Windows Server MySQL as root
-- to create a read-only user for maoffice (optional hardening step).
--
-- Usage (from Windows cmd):
--   mysql -u root -e "source setup_od_user.sql"
--
-- Replace 192.168.1.x with the actual IP of your Linux machine.

CREATE USER IF NOT EXISTS 'maoffice_reader'@'192.168.1.%'
    IDENTIFIED BY 'choose-a-strong-password-here';

GRANT SELECT ON opendental.* TO 'maoffice_reader'@'192.168.1.%';

FLUSH PRIVILEGES;

SELECT 'maoffice_reader user created with SELECT on opendental.*' AS status;
