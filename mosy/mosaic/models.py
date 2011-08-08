import os
import os.path
import re
import hashlib
import Levenshtein
import mimetypes

from itertools import combinations
from math import sqrt, log
from random import randint, uniform, shuffle, normalvariate
from PIL.ImageFile import Parser
from PIL import Image, ImageStat
from tempfile import NamedTemporaryFile

from django.core.files import File
from django.db import models, connection

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

class classproperty(property):
  def __get__(self, cls, owner):
    return self.fget.__get__(None, owner)()

class Tile(BaseImage):
  BASE_PATH = 'tile'
  CHUNK_SIZE = 10
  origin = models.ForeignKey(StockImage, related_name = '+')
  size = models.IntegerField()

  @classproperty
  @classmethod
  def RADIUS(cls):
    if not hasattr(cls, '_RADIUS'):
      cls._RADIUS = randint(1,100)
    return cls._RADIUS

  @classproperty
  @classmethod
  def TOLERANCE(cls):
    if not hasattr(cls, '_TOLERANCE'):
      cls._TOLERANCE = 8
    return cls._TOLERANCE

  @classproperty
  @classmethod
  def POINTS(cls):
    if not hasattr(cls, '_POINTS'):
      points = cls.objects.all()
      temp = {}
      for p in points:
        p.mono_list, p.rgb_list, p.str_list
        temp[p.id] = p
      cls._POINTS = temp
    return cls._POINTS

  @classmethod
  def distance(cls, tile_a, tile_b):
    weights = (
      (18.56569, 11.86457),
      (16.26291, 21.83507),
      (25.23813, 18.94915),
      (27.06847, 17.89424),
      (30.59219, 24.93490),
      (17.26454, 18.09663),
      )
    d = 0.0
    for weight in weights:
      d += cls.compare(tile_a, tile_b, weight)
    return d/len(weights)

  @classmethod
  def compare(cls, tile_a, tile_b, weight = None, equal = False):
    assert tile_a.size == tile_b.size
    if weight == None:
      if equal:
        weight = (100.0, 100.0)
      weight = tuple([normalvariate(20, 5) for i in range(2)])
    mse = cls.mse(tile_a, tile_b)

    levenshtein = cls.levenshtein(tile_a, tile_b) * weight[0] / sum(weight)
    #psnr = cls.psnr(tile_a, tile_b, mse = mse) * weight[1] / sum(weight)
    nrmsd = cls.nrmsd(tile_a, tile_b, mse = mse) * weight[1] / sum(weight)
    
    return levenshtein + nrmsd
  
  #Calculate the levenshtein distance between the two images
  @classmethod
  def levenshtein(cls, tile_a, tile_b):
    assert tile_a.size == tile_b.size
    lv = Levenshtein.distance(tile_a.str_list, tile_b.str_list)
    return float(lv)/(len(tile_a.rgb_list))

  #Calculate the mean square error between images
  @classmethod
  def mse(cls, tile_a, tile_b):
    assert tile_a.size == tile_b.size
    tmp = sum((a-b)**2 for a, b in zip(tile_a.rgb_list, tile_b.rgb_list))
    return float(tmp)/len(tile_a.rgb_list)

  #Calculate the peak signal-to-noise ratio
  @classmethod
  def psnr(cls, tile_a, tile_b, mse = None):
    assert tile_a.size == tile_b.size
    if mse == None:
      mse = cls.mse(tile_a, tile_b)
    return 20 * log(255/sqrt(mse), 10)

  @classmethod
  def nrmsd(cls, tile_a, tile_b, mse = None):
    assert tile_a.size == tile_b.size
    if mse == None:
      mse = cls.mse(tile_a, tile_b)
    return sqrt(mse) / 255

  @property
  def nn(self):
    if not hasattr(self, '_nn'):
      nn = None
      for other in Tile.POINTS:
        if other.id == self.id:
          continue
        other.distance = Tile.distance(self, other)
        if nn == None or other.distance < nn.distance:
          nn = other
      self._nn = nn
    return self._nn

  def get_nn(self, weight = None, debug = False):
    nn = None
    for other in Tile.POINTS:
      if other.id == self.id:
        continue
      other.distance = Tile.compare(self, other, weight)
      if not nn or other.distance < nn.distance:
        nn = other
        if debug:
          print "New Neighbor: %i - %f"%(other.id, other.distance)
    return nn

  @property
  def knn(self):
    if not hasattr(self, '_knn'):
      neighbors = []
      for other in Tile.POINTS:
        if other.id == self.id:
          continue
        other.distance = Tile.distance(self, other)
        if len(neighbors) < 200 or other.distance < neighbors[0].distance:
          neighbors.append(other)
          neighbors = sorted(neighbors, key = lambda p: p.distance)
          neighbors = neighbors[:200]
          neighbors.reverse()
      self._knn =  [n.id for n in neighbors]
      return self._knn

  def get_knn(self, weight = None, points = None):
    neighbors = []
    for other in Tile.POINTS:
      if other.id == self.id:
        continue
      other.distance = Tile.compare(self, other, weight)
      if len(neighbors) < 200 or other.distance < neighbors[0].distance:
        neighbors.append(other)
        neighbors = sorted(neighbors, key = lambda p: p.distance)
        neighbors = neighbors[:200]
        neighbors.reverse()
    return [n.id for n in neighbors]
    
  @property
  def pixel_map(self):
    if not hasattr(self, '_pixel_map'):
      size = self.size / self.CHUNK_SIZE
      assert size * self.CHUNK_SIZE == self.size
      pixel_map = []
      for y in range(size):
        pixels = []
        for x in range(size):
          index = (y*size+x)*3
          r, g, b = self.rgb_list[index:index+3]
          pixel = '#%0.2X%0.2X%0.2X'%(int(r), int(g), int(b))
          pixels.append(pixel)
        pixel_map.append(tuple(pixels))
      self._pixel_map = tuple(pixel_map)
    return self._pixel_map
    

  @property
  def rgb_list(self):
    assert self.size % self.CHUNK_SIZE == 0
    if not hasattr(self, '_rgb_list'):
      self.image.open('rb')
      im = Image.open(self.image.file)
      im.load()
      self.image.close()

      if im.mode in ('P', 'RGBA'):
        im = im.convert('RGB')

      self._rgb_list = []
      if im.mode == 'L':
        for val in self.mono_list:
          self._rgb_list += [val]*3
      else:
        for y in range(0, self.image.height, self.CHUNK_SIZE):
          for x in range(0, self.image.width, self.CHUNK_SIZE):
            self._rgb_list += ImageStat.Stat(im.crop((x, y, x+10, y+10))).mean
      self._rgb_list = tuple(self._rgb_list)
    assert len(self._rgb_list) == (self.size/self.CHUNK_SIZE)**2*3
    return self._rgb_list

  @property
  def address(self):
    return self.rgb_list

  @property
  def mono_list(self):
    assert self.size % self.CHUNK_SIZE == 0
    if not hasattr(self, '_mono_list'):
      self.image.open('rb')
      im = Image.open(self.image.file)
      im.load()
      self.image.close()

      im = im.convert('L')
      self._mono_list = []
      for y in range(0, self.image.height, self.CHUNK_SIZE):
        for x in range(0, self.image.width, self.CHUNK_SIZE):
          self._mono_list += ImageStat.Stat(im.crop((x, y, x+10, y+10))).mean
      self._mono_list = tuple(self._mono_list)
    assert len(self._mono_list) == (self.size/self.CHUNK_SIZE)**2
    return self._mono_list

  @property
  def str_list(self):
    if not hasattr(self, '_str_list'):
      self._str_list = ''.join([chr(int(round(x))) for x in self.rgb_list])
    return self._str_list

class CompareMethod(TimeStampable):
  mother = models.ForeignKey('self', related_name = 'mother_of', null = True)
  father = models.ForeignKey('self', related_name = 'father_of', null = True)

  lw = models.FloatField()
  nw = models.FloatField()


  @classmethod
  def generate(cls, count = 1):
    gens = []
    while len(gens) < count:
      x, created = cls.objects.get_or_create(
        lw = normalvariate(20, 5),
        nw = normalvariate(20, 5),
        )
      if created:
        gens.append(x)
    return gens

  @property
  def weight(self):
    return self.lw, self.nw

  def generate_tests(self, other, count = 20, next_group = None):
    tests = []
    for i in range(count):
      tile = Tile.objects.order_by('?')[:1].get()
      methods = [self, other]
      shuffle(methods)
      method_a, method_b = methods
      tile_a = tile.get_nn(weight = method_a.weight)
      tile_b = tile.get_nn(weight = method_b.weight)

      if tile_a == tile_b:
        x, created = CompareTest.objects.get_or_create(
          winner = method_a,
          sample_group = next_group,
          target = tile,
          tile_a = tile_a,
          tile_b = tile_b,
          method_a = method_a,
          method_b = method_b,
          )
        print "Methods too similar.  Tiles matched"
        continue

      x, created = CompareTest.objects.get_or_create(
        sample_group = next_group,
        target = tile,
        tile_a = tile_a,
        tile_b = tile_b,
        method_a = method_a,
        method_b = method_b,
        )
      if created:
        tests.append(x)
    return tests

  @classmethod
  def evolve(cls):
    sample_group = CompareTest.current_group()
    if cls.objects.count() < 15 and CompareTest.objects.filter(winner = None).count() == 0:
      cls.generate(15 - cls.objects.count())
      parents = cls.objects.all()
      for hash_a, hash_b in combinations(parents, 2):
        hash_a.generate_tests(hash_b, next_group = sample_group + 1)
    elif not CompareTest.objects.filter(winner = None).count():
      cursor = connection.cursor()
      winners = []
      for group in range(sample_group, 0, -1):
        cursor.execute('SELECT DISTINCT sample_group, winner_id, count(winner_id) AS win_count FROM mosaic_comparetest WHERE sample_group=%s GROUP BY winner_id ORDER BY win_count DESC LIMIT 0,15', [sample_group, ])
        winners += [winner[0] for winner in cursor.fetchall()]
        if len(winners) > 15:
          break
      winners = winners[:15]
      parents = list(CompareMethod.objects.filter(pk__in = winners))
      parents += list(CompareMethod.generate(10))
      for hash_a, hash_b in combinations(parents, 2):
        hash_a.generate_tests(hash_b, next_group = sample_group + 1)


  @classmethod
  def breed(cls, method_a, method_b):
    score_a = method_a.score
    score_b = method_b.score
    if score_a < score_b:
      x = cls.breed(method_b, method_a)
    else:
      weight_a = max(score_a/(score_a + score_b), 0.1)
      weight_b = max(score_b/(score_a + score_b), 0.1)

      x = cls()
      for val in ('lw', 'nw'):
        setattr(x, val, (getattr(method_a, val) + getattr(method_b, val))/2)

      x, created = cls.objects.get_or_create(
        lw = x.lw,
        nw = x.nw,
        )
      if created:
        x.father = method_a
        x.mother = method_b
        x.save()
      else:
        print "Duplicate Offspring - Father(%i) : Mother(%i)"%(method_a.id, method_b.id)
    return x

  @property
  def score(self):
    if not hashattr(self, '_score'):
      self._score = CompareTest.objects.filter(winner = self).count()
    return self._score

class CompareTest(TimeStampable):
  sample_group = models.IntegerField()
  target = models.ForeignKey(Tile)
  tile_a = models.ForeignKey(Tile, related_name = '+')
  tile_b = models.ForeignKey(Tile, related_name = '+')

  winner = models.ForeignKey(CompareMethod, related_name = '+', null = True)
  method_a = models.ForeignKey(CompareMethod, related_name = '+')
  method_b = models.ForeignKey(CompareMethod, related_name = '+')

  @classmethod
  def current_group(cls):
    if not cls.objects.count():
      return 0
    return cls.objects.latest('created_at').sample_group
