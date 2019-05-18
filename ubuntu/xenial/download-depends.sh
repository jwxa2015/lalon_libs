function getDepends()
{
   # use tr to del < >
   ret=`apt-cache depends $1|grep Depends |cut -d: -f2 |tr -d "<>"`
   echo $ret
}

for var in $*
do

  libs=$var
  echo "download $libs"
  # download libs dependen. deep in 3
  i=0
  while [ $i -lt 8 ] ;
  do
    let i++
    echo $i
    # download libs
    newlist=" "
    for j in $libs
    do
      added="$(getDepends $j)"
      echo "$j depended $added"
      newlist="$newlist $added"
      echo "download $j"
      apt-get download $j 
    done

    libs=$newlist
  done
done
