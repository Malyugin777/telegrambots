#!/bin/bash

# SSL Certificate initialization script for Nexus Project
# Run this ONCE on first deployment to get Let's Encrypt certificates

# === CONFIGURATION ===
domains=(admin.example.com)  # Change to your domain
email="your-email@example.com"  # Change to your email
staging=0  # Set to 1 for testing (to avoid rate limits)

# === DO NOT EDIT BELOW ===

data_path="./certbot"
rsa_key_size=4096

if [ -d "$data_path/conf/live/${domains[0]}" ]; then
  echo "Existing certificates found. Skipping..."
  exit 0
fi

echo "### Creating directories..."
mkdir -p "$data_path/conf"
mkdir -p "$data_path/www"

echo "### Downloading recommended TLS parameters..."
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "$data_path/conf/options-ssl-nginx.conf"
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "$data_path/conf/ssl-dhparams.pem"

echo "### Creating dummy certificate for ${domains[0]}..."
path="/etc/letsencrypt/live/${domains[0]}"
mkdir -p "$data_path/conf/live/${domains[0]}"

docker compose run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1 \
    -keyout '$path/privkey.pem' \
    -out '$path/fullchain.pem' \
    -subj '/CN=localhost'" certbot

echo "### Starting nginx..."
docker compose up --force-recreate -d nginx

echo "### Deleting dummy certificate..."
docker compose run --rm --entrypoint "\
  rm -Rf /etc/letsencrypt/live/${domains[0]} && \
  rm -Rf /etc/letsencrypt/archive/${domains[0]} && \
  rm -Rf /etc/letsencrypt/renewal/${domains[0]}.conf" certbot

echo "### Requesting Let's Encrypt certificate..."

# Join domains for -d flags
domain_args=""
for domain in "${domains[@]}"; do
  domain_args="$domain_args -d $domain"
done

# Staging mode for testing
if [ $staging != "0" ]; then staging_arg="--staging"; fi

docker compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $domain_args \
    --email $email \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --force-renewal" certbot

echo "### Reloading nginx..."
docker compose exec nginx nginx -s reload

echo "### Done! SSL certificates installed."
