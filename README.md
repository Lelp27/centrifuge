# Length-based Centrifuge Kraken report

The source code is from [DaehwanKimLab](https://github.com/DaehwanKimLab/centrifuge)

original centrifuge calculate taxonomy weight based-on count.\
in long-read sequencing, every read have differnt length so that\
change it from read-count based to read-length based weight.

only one change is in centrifuge-kreport script.

## Usage

install the original centrifuge.\
then, change centrifuge-kreport script within this page.

## docker image

[docker hub](https://hub.docker.com/repository/docker/tjdrns27/centrifuge)
`tjdrns27/centrifuge:v0.2`
