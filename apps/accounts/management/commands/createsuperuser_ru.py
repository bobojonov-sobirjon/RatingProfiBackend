"""
Rus tilida superuser yaratish komandasi
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Суперпользователь создание (русский язык)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--phone',
            type=str,
            help='Телефонный номер',
            required=True
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Пароль',
            required=False
        )

    def handle(self, *args, **options):
        phone = options['phone']
        password = options.get('password')
        
        if User.objects.filter(phone=phone).exists():
            self.stdout.write(
                self.style.ERROR(f'Пользователь с телефоном {phone} уже существует!')
            )
            return
        
        if not password:
            from getpass import getpass
            password = getpass('Пароль: ')
            password_again = getpass('Пароль (повторно): ')
            if password != password_again:
                self.stdout.write(
                    self.style.ERROR('Пароли не совпадают!')
                )
                return
        
        try:
            user = User.objects.create_superuser(
                phone=phone,
                password=password,
                role='admin',
                is_phone_verified=True,
                is_active=True,
                is_staff=True,
                is_superuser=True
            )
            self.stdout.write(
                self.style.SUCCESS(f'Суперпользователь успешно создан: {phone}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при создании пользователя: {str(e)}')
            )
