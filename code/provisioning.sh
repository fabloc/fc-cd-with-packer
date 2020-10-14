#!/bin/sh
apt update -y
apt install apache2 -y

#Download ossutil used for downloading files from OSS
wget http://gosspublic.alicdn.com/ossutil/1.6.19/ossutil64
chmod 755 ossutil64
#Configure ossutil with RAM user credentials.
./ossutil64 config -e oss-eu-central-1.aliyuncs.com -i "$ALICLOUD_ACCESS_KEY" -k "$ALICLOUD_SECRET_KEY" -t "$SECURITY_TOKEN" -L EN
cat .ossutilconfig
#Download the file(s) from bucket "a365-ci-cd". The RAM user MUST be allowed to access the bucket
#ossutil with -f forces the actions without user interaction (otherwise it will ask if you want to overwrite the existing index.html)
./ossutil64 cp oss://$PATH_TO_RELEASE /var/www/html/index.html -f

systemctl start apache2
systemctl enable apache2