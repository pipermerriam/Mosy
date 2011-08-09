from django.db import models, connection, transaction
from django.db.models import Q, F

from mosy.pof.fields import PickledObjectField

from itertools import combinations
from random import normalvariate, uniform, randint, shuffle, sample, choice
from math import sqrt, floor
from threading import Thread
from time import time

from mosy.mosaic.models import Tile

# Create your models here.

RADIUS = 3.4
TOLERANCE = 1.2

'''

LSH requires a model with the following functions

Foo.distance(obj_1, obj_2)
- Given two objects, returns a measurement of their similarity.
  return value of zero means they are identical, and higher 
  numbers mean less simlarity.
@param obj_1
@param obj_2

Foo.get_points()
- Returns a dictionary of all points

LSH requires the following properties

Foo().address
- Returns an iterable of numeric values representing the objects
  'location' in the point space.

Foo.RADIUS
- Distance value for which two points should be considered 'close'

Foo.TOLERANCE
- Scalar for RADIUS value for when two points should be considered
  'far apart'

'''
PointModel = Tile

class LSH(models.Model):
  father = models.ForeignKey('self', related_name = 'father_of', null = True)
  mother = models.ForeignKey('self', related_name = 'mother_of', null = True)
  p1 = models.FloatField(null = True)
  p2 = models.FloatField(null = True)
  collisions = models.FloatField(null = True)

  tested = models.BooleanField(default = False)

  a = PickledObjectField(null = True)
  r = models.IntegerField(null = True)
  b = models.FloatField(null = True)
  mean = models.FloatField(null = True)
  std = models.FloatField(null = True)

  @property
  def score(self):
    if self.p1 == None or self.p2 == None:
      return False
    return self.p1 - self.p2

  @property
  def generation(self):
    gen =  0
    if not self.father and not self.mother:
      return gen
    if self.father:
      gen = self.father.generation + 1
    if self.mother:
      gen = max(gen, self.mother.generation + 1)
    return gen

  @classmethod
  def evolve(cls):
    PointModel.init()
    while True:
      test_list = cls.objects.defer('father', 'mother').filter(tested = False)
      if test_list.exists():
        test_list = list(test_list)
        while test_list:
          lsh = test_list.pop()
          lsh.test()
        print "Testing untested hash functions"
      elif cls.objects.count() < PointModel.INITIAL_POPULATION:
        print "Generating Initial Population"
        for i in range(PointModel.INITIAL_POPULATION-cls.objects.count()):
          x = cls()
          x.test()
      else:
        print "Breeding New Generation"
        cls.spawn()

  @classmethod
  def spawn(cls, top = 60, other = 10):
    parents_query = cls.objects.raw('SELECT id, collisions, a, b, r, mean, std, p1, p2 FROM knn_lsh ORDER BY p1-p2 DESC LIMIT 0, %s', [top])
    parents = [lsh for lsh in parents_query]
    print "Grabbing random breeders"
    for i in range(other):
      new_breeder = cls()
      new_breeder.test()
      parents.append(new_breeder)
    assert len(parents) == top + other
    for hash_a, hash_b in combinations(parents, 2):
      print "Breeding (%i: %f) and (%i: %f)"%(hash_a.id, hash_a.score, hash_b.id, hash_b.score)
      child = cls.breed(hash_a, hash_b)
    

  @classmethod
  def breed(cls, hash_a, hash_b):
    score_a = hash_a.score
    score_b = hash_b.score
    if score_b > score_a:
      return breed(hash_b, hash_a)
    weight_a = score_a/(score_a + score_b)
    weight_b = score_b/(score_a + score_b)
    
    x = cls()
    x.father = hash_a
    x.mother = hash_b
    for val in ('b', 'r'):
      if uniform(0, 1) <= weight_a:
        setattr(x, val, getattr(hash_a, val))
      else:
        setattr(x, val, getattr(hash_b, val))

    if x.b > x.r:
      x.b = uniform(0, x.r)

    if randint(1, 100) >= 99:
      for val in ('mean', 'std'):
        if uniform(0, 1) <= weight_a:
          setattr(x, val, getattr(hash_a, val))
        else:
          setattr(x, val, getattr(hash_b, val))
      x.a = [normalvariate(x.mean, x.std) for i in range(len(hash_a.a))]
    else:
      x.a = []
      for i in range(len(hash_a.a)):
        if uniform(0, 1) <= weight_a:
          x.a.append(hash_a.a[i])
        else:
          x.a.append(hash_b.a[i])
      x.mean = sum(x.a)/float(len(x.a))
      x.std = 0.0
      for val in x.a:
        x.std += (val - x.mean)**2
      x.std /= len(x.a)
      x.std = sqrt(x.std)

    if x.a == hash_a.a and x.b == hash_a.b and x.r == hash_a.r:
      print "Duplicate Offspring"
      return 
    if x.a == hash_b.a and x.b == hash_b.b and x.r == hash_b.r:
      print "Duplicate Offspring"
      return

    x.save()
    return x

  def generate(self, mean = None, std = None, dimension = 48):
    if not mean == None:
      self.mean = mean
    else:
      self.mean = floor(uniform(-128, 128))
    if not std == None:
      self.std = std
    else:
      self.std = floor(uniform(1, 64))
    self.a = [normalvariate(self.mean, self.std) for i in range(dimension)]
    self.r = floor(uniform(2, 32768))
    self.b = uniform(0, self.r)
    self.save()

  def project(self, point):
    vector = point.address
    if self.a == None or self.b == None or self.r == None:
      if not self.mother and not self.father:
        self.generate(dimension = len(vector))
    dp = sum([x*y for x, y in zip(self.a, vector)])
    return floor((dp + self.b)/float(self.r))

  def test(self, early_exit = True):
    start_time = time()
    if early_exit and LSH.objects.count() >= PointModel.INITIAL_POPULATION:
      cursor = connection.cursor()
      cursor.execute("SELECT p1-p2 AS `score` FROM `knn_lsh` ORDER BY p1-p2 DESC LIMIT 1000,1")
      target_score = float(cursor.fetchone()[0])
    else:
      early_exit = False
    sample_set = sample(PointModel.POINTS.keys(), 200)
    p1_overall = 0.0
    p2_overall = 0.0
    p3_overall = 0.0
    collisions_overall = 0.0

    for n in range(len(sample_set)):
      test_point = PointModel.POINTS[sample_set.pop()]
      test_point.projection = self.project(test_point)

      close_points = test_point.knn

      sample_points = PointModel.POINTS.keys()
      for point in close_points:
        sample_points.remove(point)
      sample_points.remove(test_point.id)
      sample_points = sample(sample_points, 200)
      sample_points += close_points
      sample_points = [PointModel.POINTS[p] for p in sample_points]

      assert len(sample_points) == 400
      for point in sample_points:
        point.distance = PointModel.distance(test_point, point)
        point.projection = self.project(point)

      shuffle(sample_points)

      collisions = 0
      p1_count = 0
      p2_count = 0
      p3_count = 0
      for i in range(400):
        point = sample_points[i]
        if test_point.projection == point.projection:
          collisions += 1
          if point.distance <= PointModel.RADIUS:
            p1_count += 1
          elif point.distance >= PointModel.RADIUS*PointModel.TOLERANCE:
            p2_count += 1
          else:
            p3_count += 1
      p1_overall = (p1_overall*n+p1_count)/(n+1)
      p2_overall = (p2_overall*n+p2_count)/(n+1)
      p3_overall = (p3_overall*n+p3_count)/(n+1)
      collisions_overall = (collisions_overall*n+collisions)/(n+1)
      if early_exit and n >= 80:
        if p1_overall - p2_overall < target_score*(float(n)/200-0.2):
          print "Early Exit Criteria Met at %i"%n
          break

    self.collisions = collisions_overall
    self.tested = True
    if collisions_overall > 0:
      self.p1 = p1_overall
      self.p2 = p2_overall
    self.save()

    print "LSH(%i) - Test_Time: %f"%(self.id, time() - start_time)
    #print "Colisions: %i - P1: %i P2: %i P3: %i"%(int(collisions_overall), int(p1_overall), int(p2_overall), int(p3_overall))
