mkdir -p certs
SAN="DNS:localhost"
while IFS= read -r IP; do
  [ -n "$IP" ] && SAN="$SAN,IP:$IP"
done < ip.txt
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/local.key -out certs/local.crt -days 825 \
  -subj "/CN=ImageBlinds" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth" \
  -addext "subjectAltName=$SAN"