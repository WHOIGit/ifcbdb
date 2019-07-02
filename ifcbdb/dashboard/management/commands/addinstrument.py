from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Instrument

class Command(BaseCommand):
    help = 'add instrument'

    def add_arguments(self, parser):
        parser.add_argument('number', type=int, help='instrument number')
        parser.add_argument('-ip', '--ip', type=str, help='ip address or DNS name')
        parser.add_argument('-u', '--username', type=str, help='username')
        parser.add_argument('-p', '--password', type=str, help='password')
        parser.add_argument('-s', '--share', type=str, help='share name')
        parser.add_argument('-n', '--nickname', type=str, help='nickname')

    def handle(self, *args, **options):
        number = options['number']
        ip = options['ip']
        username = options['username']
        password = options['password']
        share = options['share']
        nickname = options['nickname']

        if number < 10:
            version = 1
        else:
            version = 2

        try:
            i = Instrument.objects.get(number=number)
        except Instrument.DoesNotExist:
            i = Instrument(number=number, version=version)
        if ip:
            i.address = ip
        if username:
            i.username = username
        if password:
            i.password = password
        if share:
            i.share = share
        if nickname:
            i.nickname = nickname

        i.save()

        print('Created or updated IFCB{}'.format(number))

