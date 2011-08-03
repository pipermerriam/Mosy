from django.db import models, connection, transaction
from django.db.models import Q, F

from mosy.pof.fields import PickledObjectField

from itertools import combinations
from random import normalvariate, uniform, randint, shuffle, sample, choice
from math import sqrt, floor
from threading import Thread
from time import time

# Create your models here.

RADIUS = 300
TOLERANCE = 1.2

class DataPoint(models.Model):
  vector = PickledObjectField()

  @classmethod
  def get_plist(cls):
    plist = {}
    for p in cls.objects.iterator():
      p.neighbors = Neighbors.objects.get(point = p).neighbors
      plist[p.id] = p
    return plist

  def get_knn(self, points = None, debug = False):
    if not points:
      points = DataPoint.objects.all()
    neighbors = []
    for dp in points:
      if dp.id == self.id:
        continue
      dp.distance = self.dist(dp)
      if len(neighbors) < 200 or dp.distance < neighbors[0].distance:
        neighbors.append(dp)
        neighbors = sorted(neighbors, key = lambda p: p.distance)
        neighbors = neighbors[:200]
        neighbors.reverse()
        if debug:
          print "New Neighbor: %i - %f"%(dp.id, dp.distance)
    nl = [n.id for n in neighbors]
    n, created = Neighbors.objects.get_or_create(point = self)
    if created:
      n.neighbors = nl
      n.save()
    return neighbors

  def dist(self, other, exact = False):
    d = 0
    for a, b in zip(self.vector, other.vector):
      d += (a-b)**2
    return sqrt(d)

class Neighbors(models.Model):
  point = models.ForeignKey(DataPoint)
  neighbors = PickledObjectField()

class LSH(models.Model):
  father = models.ForeignKey('self', related_name = 'father_of', null = True)
  mother = models.ForeignKey('self', related_name = 'mother_of', null = True)
  p1 = models.FloatField(null = True)
  p2 = models.FloatField(null = True)
  collisions = models.FloatField(null = True)

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
    plist = DataPoint.get_plist()
    while True:
      if cls.objects.count() < 4000:
        if cls.objects.filter(collisions = None):
          for x in cls.objects.filter(collisions = None):
            x.test(plist = plist)
        print "Generating Base Objects"
        for i in range(4000-cls.objects.count()):
          x = cls()
          x.test(plist = plist)
      null_query = cls.objects.defer('father', 'mother').filter(collisions = None)
      if null_query.exists():
        assert len(null_query)
        print "Testing New Children"
        for lsh in null_query:
          lsh.test(plist = plist)
      print "Generating Parents for new Generations"
      cls.spawn(plist = plist)

  @classmethod
  def spawn(cls, top = 60, other = 10, plist = None):
    if plist == None:
      plist = DataPoint.get_plist()
    parents_query = cls.objects.raw('SELECT id, collisions, a, b, r, mean, std, p1, p2 FROM knn_lsh ORDER BY p1-p2 DESC LIMIT 0, %s', [top])
    parents = [lsh for lsh in parents_query]
    print "Grabbing random breeders"
    for i in range(other):
      new_breeder = cls()
      new_breeder.test(plist = plist)
      parents.append(new_breeder)
    assert len(parents) == top + other
    for hash_a, hash_b in combinations(parents, 2):
      if hash_a.score > hash_b.score:
        father = hash_a
        mother = hash_b
      else:
        father = hash_b
        mother = hash_a
      child = cls.breed(father, mother)
      print "Breeding Father(%i: %f) and Mother(%i: %f)"%(father.id, father.score, mother.id, mother.score)
    

  @classmethod
  def breed(cls, hash_a, hash_b):
    score_a = hash_a.score
    score_b = hash_b.score
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

  def project(self, v):
    if self.a == None or self.b == None or self.r == None:
      if not self.mother and not self.father:
        self.generate()
    dp = sum([x*y for x, y in zip(self.a, v)])
    return floor((dp + self.b)/float(self.r))

  def test(self, plist = None, early_exit = True):
    if plist == None:
      plist = DataPoint.get_plist()
    start_time = time()
    if early_exit:
      cursor = connection.cursor()
      cursor.execute("SELECT p1-p2 AS `score` FROM `knn_lsh` ORDER BY p1-p2 DESC LIMIT 1000,1")
      target_score = float(cursor.fetchone()[0])
    sample_set = sample(range(1, 5001), 200)
    p1_overall = 0.0
    p2_overall = 0.0
    p3_overall = 0.0
    collisions_overall = 0.0

    for n in range(len(sample_set)):
      #test_point = DataPoint.objects.get(pk = sample_set.pop())
      test_point = plist[sample_set.pop()]
      test_point.projection = self.project(test_point.vector)

      #close_points = Neighbors.objects.get(point = test_point).neighbors
      close_points = test_point.neighbors

      points = range(1, 5001)
      for point in close_points:
        points.remove(point)
      points.remove(test_point.id)
      points = sample(points, 200)
      points += close_points
      points = [plist[p] for p in points]
      #points = list(DataPoint.objects.filter(pk__in = points))

      assert len(points) == 400
      for point in points:
        point.distance = test_point.dist(point)
        point.projection = self.project(point.vector)

      shuffle(points)

      collisions = 0
      p1_count = 0
      p2_count = 0
      p3_count = 0
      for i in range(400):
        point = points[i]
        if test_point.projection == point.projection:
          collisions += 1
          if point.distance <= RADIUS:
            p1_count += 1
          elif point.distance >= RADIUS*TOLERANCE:
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
    if collisions_overall > 0:
      self.p1 = p1_overall
      self.p2 = p2_overall
    self.save()

    print "LSH(%i) - Test_Time: %f"%(self.id, time() - start_time)
    #print "Colisions: %i - P1: %i P2: %i P3: %i"%(int(collisions_overall), int(p1_overall), int(p2_overall), int(p3_overall))
