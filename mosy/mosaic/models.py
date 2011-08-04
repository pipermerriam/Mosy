import os
import os.path
import re
import hashlib

from random import randint
from PIL.ImageFile import Parser
from tempfile import NamedTemporaryFile

from django.core.files import File
from django.db import models

from mosy.behaviors.models import *

FILE_NAME = re.compile('^([0-9]+)\.(jpg|jpeg|gif|bmp|png)$')

def upload_to(instance, filename):
  return os.path.join(instance.BASE_PATH , '%s'%randint(100, 199), '%s'%randint(100, 199), os.path.basename(filename))

class BaseImage(TimeStampable)
  image = models.ImageField(upload_to = upload_to)
  hash = models.CharField(max_length = 256, null = True)

  class Meta:
    abstract = True

  @property
  def extension(self):
    if not hasattr(self, '_extension'):
      pass
    return self._extension

  @classmethod
  def hash_image(cls, f):
    f.seek(0)
    file_hasher = hashlib.sha256()
    while True:
      buf = f.read(8192)
      if buf:
        file_hasher.update(buf)
        continue
      break
    return file_hasher.hexdigest()

class StockImage(BaseImage):
  BASE_PATH = 'stock'

  @property
  def mimetype(self):
    if not hasattr(self, '_mimetype'):
      pass
    return self._mimetype


  @classmethod
  def crawl(cls, directory):
    for entry in os.listdir(directory):
      abs_path = os.path.join(directory, entry)
      if os.path.isdir(abs_path):
        cls.crawl(abs_path)
      elif os.path.isfile(abs_path) and FILE_NAME.match(entry):
        print "Importing %s"%abs_path
        try:
          cls.import_image(abs_path)
        except IOError:
          print "IOError"

  @classmethod
  def import_image(cls, file_path):
    image_parser = Parser()

    f = open(file_path, 'rb')
    while True:
      buf = f.read(8192)
      if buf:
        image_parser.feed(buf)
        continue
      break
    image_parser.close()
    im_hash = cls.hash_image(f)
    if cls.objects.filter(hash = im_hash).exists():
      print "Skipping duplicate (%s)"%im_hash
    else:
      cls.objects.create(
        image = File(f),
        hash = im_hash,
        )

  def export_tile(self, tile_size):
    pass

class Tile(BaseImage):
  BASE_PATH = 'tile'
