#! /bin/bash


cp -r $INSTALL_LIBS $LALON_HOME/repo

mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled

NGINXCONFIG=/etc/nginx/sites-available/repo.conf
touch $NGINXCONFIG
ln -fs $NGINXCONFIG /etc/nginx/sites-enabled/repo.conf
NGINXUG='www-data:www-data'
NGINXUSER='www-data'

cat > $NGINXCONFIG <<EOF
server {
    listen       9181;
    server_name  _;
    
   	access_log /var/log/nginx/lalon_repo.access.log;
   	error_log /var/log/nginx/lalon_repo.error.log;

    root /opt/www;

    location  / {
      root $LALON_HOME/repo/ubuntu;
      autoindex on;
      expires 5h;
    }

}
EOF
