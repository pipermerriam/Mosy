import os
import os.path
import re
import hashlib
import Levenshtein
import mimetypes

from random import randint
from PIL.ImageFile import Parser
from PIL import Image
from tempfile import NamedTemporaryFile

from django.core.files import File
from django.db import models

from mosy.behaviors.models import *

FILE_NAME = re.compile('^([0-9]+)\.(jpg|jpeg|gif|bmp|png)$')

def upload_to(instance, filename):
  return os.path.join(instance.BASE_PATH , '%s'%randint(100, 199), '%s'%randint(100, 199), os.path.basename(filename))

class BaseImage(TimeStampable):
  image = models.ImageField(upload_to = upload_to)
  hash = models.CharField(max_length = 256, null = True)

  class Meta:
    abstract = True

  @property
  def extension(self):
    if not hasattr(self, '_extension'):
      self._extension = os.path.basename(self.image.path).rsplit('.',1).pop()
    return self._extension

  @property
  def mimetype(self):
    if not hasattr(self, '_mimetype'):
      if hasattr(self, '_extension'):
        self._extension = os.path.basename(self.image.path).rsplit('.', 1).pop()
      mimetypes.init()
      self._mimetype = mimetypes.types_map[os.extsep + self.extension]
    return self._mimetype

  @property
  def filename(self):
    if not hasattr(self, '_filename'):
      self._filename = os.path.basename(self.image.path).rsplit('.', 1)[0]
    return self._filename

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
    self.image.open('r')
    im = Image.open(self.image.file)
    x_size, y_size = im.size
    if x_size < tile_size or y_size < tile_size:
      print "Image dimensions (%ix%i) smaller than desired tile size(%i)"%(x_size, y_size, tile_size)
      return False
    if x_size > y_size:
      ul = int(round((x_size-y_size)/2.0))
      ur = 0
      ll = int(round((x_size-y_size)/2.0+y_size))
      lr = y_size
    elif y_size > x_size:
      ul = 0
      ur = 0
      ll = x_size
      lr = x_size

    if not x_size == y_size:
      im.crop((ul, ur, ll, lr))
    im = im.resize((tile_size, tile_size))
    tmp_file = NamedTemporaryFile(prefix = self.filename, suffix = os.extsep + self.extension)
    im.save(tmp_file)
    im_hash = StockImage.hash_image(tmp_file)
    if Tile.objects.filter(hash = im_hash).exists():
      print "Tile Already Exists (%s)"%im_hash
    else:
      im = File(tmp_file)
      Tile.objects.create(
        image = im,
        hash = im_hash,
        origin = self,
        size = tile_size,
        )

class Tile(BaseImage):
  BASE_PATH = 'tile'
  origin = models.ForeignKey(StockImage, related_name = '+')
  size = models.IntegerField()

  #Calculate the levenshtein distance between the two images
  @classmethod
  def levenshtein(cls, tile_a, tile_b):
    assert tile_a.size == tile_b.size
    return Levenshtein.distance(tile_a.str_list, tile_b.str_list)

  #Calculate the mean square error between images
  @classmethod
  def mse(cls, tile_a, tile_b):
    pass

  #Calculate the peak signal-to-noise ratio
  @classmethod
  def psnr(cls, tile_a, tile_b):
    pass

  @classmethod
  def nrmsd(cls, tile_a, tile_b):
    pass

  @property
  def rgb_list(self):
    if not hasattr(self, '_rgb_list'):
      pass
    return self._rgb_list

  @property
  def mono_list(self):
    if not hasattr(self, '_mono_list'):
      pass
    return self._mono_list

  def str_list(self):
    if not hasattr(self, '_str_list'):
      self._str_list = ''.join([chr(int(x)) for x in self.mono_list])
    return self._str_list
