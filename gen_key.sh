#!/bin/bash

arch=`lsb_release -c -s`
apt-ftparchive packages $arch/. > $arch/Packages
cd $arch
gzip -c Packages > Packages.gz

cd ..

apt-ftparchive release $arch/. > $arch/Release
cd $arch
gpg --clearsign -o InRelease Release
gpg -abs -o Release.gpg Release

cd ..
scp -P 2200 xenial/* qgw@192.168.122.1:/home/qgw/work/code/Shujiang/deploy/Install/libs/ubuntu/xenial/
