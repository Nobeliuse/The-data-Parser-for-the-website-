import requests
import re
import time
import copy
from datetime import datetime
from store.settings import API_TOKEN, VERSION, OWNER_ID
from .models import *
from django.core.exceptions import ObjectDoesNotExist
from django.utils.crypto import get_random_string
from django.core.files.base import ContentFile


class HandlerGoods:
    clothes = {
            'title': '',
            'size': '',
            'price': '',
            'pack': '',
            'article': ''
        }
    
    @staticmethod
    def __handler_size_other(size_other:str) -> list:
        split_size = size_other.split(',')
        new_size = []
        for one_size in split_size:
            new_size.append(one_size)
        return new_size

    @staticmethod
    def __handler_size(size:str) -> list:
        split_size = size.split('-')
        new_size = []
        for i in range(int(split_size[0]), int(split_size[1])):
            new_size.append(i)
        new_size.append(int(split_size[1]))
        return new_size

    @staticmethod
    def __calculate_new_price(price:int, percent:int) -> float:
        quarter = int(price) * percent / 100
        new_price = int(price) + quarter
        return price

    def handler_goods(self, product, one_album_title) -> dict:
        # try to understand what is the product
        product = product.split('\n')
        clothes_copy = copy.deepcopy(self.clothes)
        clothes_copy['title'] = product[0]
        print(product)
        for one_element_array in product:
            boots = re.findall(r'обувь', one_album_title.lower())
            price = re.findall(r'Цена: (\d+)руб', one_element_array)
            if boots and price != []:
                new_price = self.__calculate_new_price(int(price[0]), 30)
                clothes_copy['price'] = int(new_price)
            elif boots == [] and price != []:   
                new_price = self.__calculate_new_price(int(price[0]), 25)
                clothes_copy['price'] = int(new_price)
            size = re.findall(r'Размеры: (\d+-\d+)', one_element_array)
            article = re.findall(r'Арт:\s*(\d+)', one_element_array)
            size_other = re.findall(r'Размеры: ([\d+,]+)', one_element_array)
            pack = re.findall(r'В упаковке:(\s*\d+\s*)пар', one_element_array)
            if size:
                new_size = self.__handler_size(size[0])
                clothes_copy['size']= new_size
            if size_other and not size:
                new_size = self.__handler_size_other(size_other[0])
                clothes_copy['size'] = new_size
            if pack:
                clothes_copy['pack'] = pack[0]
            elif pack == '':
                pack = 1
            clothes_copy['article'] = article
        return clothes_copy


class CreationProduct(HandlerGoods):

    @staticmethod
    def __calculate_product_removal_time(time:int)-> int:
        """Вычисление время удаление объекта(14 дней)"""
        date_time_now = datetime.now()
        timestamp_now = int(round(date_time_now.timestamp()))
        two_weeks = int('1209600')
        date_time_removal_product = int(time) + two_weeks
        return date_time_removal_product

    @staticmethod
    def __create_image(image_url, product):
        """Сохраняет изображение в бд"""
        r = requests.get(image_url)
        image = Image.objects.create(url_image=image_url)
        random_string = get_random_string(length=2)
        image.image.save(f'{image.id}-{random_string}.jpg', ContentFile(r.content))
        product.image.add(image)

    @staticmethod
    def __create_or_get_size(array_size:list, product) -> None:
        """получает или создает модель для размера с опр значением"""
        for one_size in array_size:
            try:
                size = Size.objects.get(size=one_size)
            except ObjectDoesNotExist:
                size = Size.objects.create(size=one_size)
            product.size.add(size)

    def create_or_check_product(self, answer, one_album_title):
        """Проверка продукта на содержание в бд(если нету, то создает)"""
        for one_product in answer:
            image_url = one_product['sizes'][-1]['url']
            product_description = one_product['text']
            description_product = self.handler_goods(product_description, one_album_title)
            date_time_product = int(one_product['date'])
            date_time_removal_product = self.__calculate_product_removal_time(
                                                                date_time_product)
            print('Название альбома: ', one_album_title)
            print('Название продукта: ', description_product['title'])
            print('Цена продукта: ', description_product['price'], ' руб')
            print('Дата создание поста: ',\
                    datetime.utcfromtimestamp(date_time_product).strftime('%Y-%m-%d %H:%M:%S'))
            print('Арт: ', description_product['article'])
            if description_product['size']:
                print('Размер товара: ', description_product['size'])
            if not description_product['pack']:
                description_product['pack'] = 1
            if description_product['pack']:
                print('В упаковке: ', description_product['pack'], 'шт')
            if not description_product['article']:
                continue
            product_article = Product.objects.filter(unique_id=int(description_product['article'][0])).first()
            if product_article:
                is_exist = False
                for img in product_article.image.all():
                    if img.url_image == image_url:
                        is_exist = True
                        print('Данный объект уже существует')
                if not is_exist:
                    print("Это условие выполняется")
                    self.__create_image(image_url, product_article)
            else:
                try:
                    category = Category.objects.get(name=one_album_title)
                except ObjectDoesNotExist:
                    category = Category.objects.create(name=one_album_title)
                product = Product.objects.create(
                        title=description_product['title'],
                        price=description_product['price'],
                        unique_id=int(description_product['article'][0]),
                        category=category,
                        pack=description_product['pack'],
                        date_time_create=datetime.utcfromtimestamp(date_time_product),
                        data_removal=datetime.utcfromtimestamp(date_time_removal_product),
                    )
                self.__create_or_get_size(description_product['size'], product)
                self.__create_image(image_url, product)


class ParserData(CreationProduct):

    @staticmethod
    def __get_id_album() -> dict:
        """Получает индефикатор альбома"""
        response = requests.get('https://api.vk.com/method/photos.getAlbums',
                        params={
                            'owner_id': OWNER_ID,
                            'access_token': API_TOKEN,
                            'v': VERSION,
                        }
                    ).json()
        data_album = {
            'id': [],
            'title': []
        }
        for array in response['response']['items']:
            data_album['id'].append(array['id'])
            data_album['title'].append(array['title'])
        return data_album


    def get_photos_from_the_album(self) -> None:
        """получаем фото из одного альюома"""
        data_album = self.__get_id_album()
        index = 0
        for one_album_id in data_album['id']:
            one_album_title = data_album['title'][index]
            response = requests.get('https://api.vk.com/method/photos.get',
                        params={
                            'owner_id': OWNER_ID,
                            'album_id': one_album_id,
                            'access_token': API_TOKEN,
                            'v': VERSION,
                            'count': 6,
                        }
                    ).json()
            #print("Album name: ", one_album_title)
            answer = response['response']['items']
            #передаем список продуктов в обработчик(пусть он сам разбирается)
            self.create_or_check_product(answer, one_album_title)
            index += 1
            