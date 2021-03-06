# Django dependencies.
from django.core.serializers import serialize
from django.conf.urls.defaults import patterns, url, include

# Intra-app dependencies.
from djangocore.api.resources import BaseResource
from djangocore.transform.forms import transformer
from product_database.models import *

import django.db.models as djmodels
import inspect
import json

class BaseModelResource(BaseResource):
    max_orderings = 1 # max number of order parameters for a query
    max_objects = 500 # max number of objects returned by a query
    
    model = None
    form = None # a model form class to use when creating and updating objects
    fields = () # the fields to expose when serializing this model
    
    def __init__(self, *args, **kwargs):
        super(BaseModelResource, self).__init__(*args, **kwargs)
        
        # Throw an error if the developer forgot to set a model on the Resource
        if not self.model:
            raise TypeError("%s must specify a model attribute" %
                self.__class__.__name__)

    def get_urls(self):
        from django.conf.urls.defaults import patterns, url
        urlpatterns = patterns('',
            url('^length/$',    self.mapper,    self.ops(get='length')),
            url('^list/$',      self.mapper,    self.ops(get='list')),
            url('^form/$',      self.mapper,    self.ops(get='form')),
            url('^$',           self.mapper,    self.ops(get='show', \
              post='create', put='update', delete='destroy')),
        )
        for name in dir(self.model):
            obj = getattr(self.model, name)
            if (inspect.ismethod(obj) or inspect.isfunction(obj)):
              if obj.func_dict.get("attr")=="exposeClass":
                  urlpatterns+=patterns('', url('^'+name+"/", self.mapper, {'GET': obj}),)
        return urlpatterns

    def get_url_prefix(self):
        ops = self.model._meta
        return 'models/%s/%s/' % (ops.app_label, ops.module_name)

    def serialize_models(self, model_or_iterable, request):
        req = request.GET.copy()
        #print req
        """
        Convert a model (or list of models) into standard python types
        for later serialization.
        """
        
        iterable = True
        if not hasattr(model_or_iterable, '__iter__'):
            model_or_iterable = [model_or_iterable]
            iterable = False

        
        #if the model has methods that are exposed, add these to the serialization
        #i'm afraid that this is slower than the standard serailization above, as we do lots of
        #introspection on every line. in order to speed that up, we'll investigate the first object only,
        #and then save the values.
        #print "hargh"
        #print model_or_iterable, type(model_or_iterable)
        exposedCalls = []
        for model in model_or_iterable:
            if hasattr(model, "exposedMethods"):
                exposedCalls = model.exposedMethods
            #for name in dir(model):
                #print 43
                #print "name: ", name, "model: ", model
                #obj = getattr(model, name)
                #if inspect.ismethod(obj) or inspect.isfunction(obj):
                    #print 44
                    #if obj.func_dict.get("attr")=="expose":
                        #print 45
                        #exposedCalls.append(name)
            #break; #just the first insctance

        #now use the django serializaation, but line for line
        s = []
        if self.fields:
            # Filter the model's fields, if the resource requires it.
            if len(exposedCalls)==0:
                 s = serialize('json', model_or_iterable, fields=self.fields)
            else:
                for d in model_or_iterable:
                    sx = serialize('json', d, fields=self.fields)
                    """ and add the custom method calls """
                    for name in exposedCalls:
                        if not sx.get("fields"): break
                        sx["fields"][name] = getattr(d, name).__call__()
                        #print unicode(name), unicode(getattr(d, name))
                    s.append(sx)
        else:
            if len(exposedCalls)==0:
                #s = serialize('json', model_or_iterable)
                # find out all field_sets
                '''
                #sets = []                
                for model in model_or_iterable:
                    if (model.__class__.__name__ != 'Materialgroup' and model.__class__.__name__ != 'Price' and model.__class__.__name__ != 'Currency'):
                        fields = model._meta.get_all_related_objects()
                        for field in fields:
                            accessor = field.get_accessor_name()
                            if accessor not in sets:
                                sets.append(accessor)                       
                s = serialize('json', model_or_iterable, indent=4, relations=sets)
                '''
                
                '''
                relations = []
                # follow foreign keys
                fields = model._meta.fields
                for field in fields:
                    print type(field)
                    if (type(field)==djmodels.fields.related.ForeignKey):
                        accessor = field.name
                        print accessor
                        if accessor not in relations:
                            relations.append(accessor)
                
                # follow many to many relation // does not work with through
                fields = model._meta.many_to_many
                for field in fields:
                    if (type(field)==djmodels.fields.related.ManyToManyField):
                        accessor = field.get_attname()
                        print accessor
                        if accessor not in relations:
                            relations.append(accessor)
                
                # follow reverse foreign keys
                fields = model._meta.get_all_related_objects()
                for field in fields:
                    print field                    
                    accessor = field.get_accessor_name()
                    print accessor
                    if accessor not in relations:
                        relations.append(accessor)
                        
                # follow reverse foreign keys // does it work?
                fields = model._meta.get_all_related_many_to_many_objects()
                for field in fields:
                    print field                    
                    accessor = field.get_accessor_name()
                    print accessor
                    if accessor not in relations:
                        relations.append(accessor)
                '''

                '''                
                relations = ('template')
                relations = ('products')
                relations = ('actionproduct_set','template')
                relations = {'actionproduct_set':{}}
                relations = ['actionproduct_set']
                relations = {'actionproduct_set':{'fields':('product',)}}
                relations = {'actionproduct_set':{'fields':['product','action']}}
                relations = {'actionproduct_set':{'relations':['product','action']}}
                relations = {"template":{},"actionproduct_set":{"relations":["product","action"]}}
                '''
                
                if req.has_key('relations'):
                    relations = {}                
                    if req['relations'] != "":                    
                        org_rel = json.loads(req['relations'])                    
                        self.dict_keys_to_str(relations,org_rel)
                    
                    print relations.__class__
                    print relations
                           
                    s = serialize('json', model_or_iterable, indent=4, relations=relations)
                else:
                    s = serialize('json', model_or_iterable, indent=4)
            else:
                for d in model_or_iterable:
                    """ django can only serialize querysets... :-( """
                    try:
                        sx = serialize('json', [d])[0]
                    except:
                        continue

                    """ and add the custom method calls """
                    for name in exposedCalls:
                        if not sx.get("fields"):break
                        #print unicode(name), unicode(getattr(d, name))
                        sx["fields"][name] = getattr(d, name).__call__()
                    s.append(sx)

        # If we were given a single item, then we return a single item.
        #if iterable == False:
            #s = s[0]
        return s
    
    def dict_keys_to_str(self,new_dict,org_dict):
        for key in org_dict.keys():
            new_key = str(key)
            org_val = org_dict[key]
            if type(org_val) == type({}):
                new_val = {}
                self.dict_keys_to_str(new_val,org_val)
                new_dict[new_key] = new_val
            else:
                new_dict[new_key] = org_dict[key]
            
        
    
    def process_lookups(self, lookups):
        """
        GET parameter keys are unicode strings, but we can only pass in
        strings as keyword arguments, so we convert them here.
        
        """
        return dict([(str(k), v) for k, v in lookups.items()])
                
    def get_query_set(self, request):
        return self.model._default_manager.all()
    
    def length(self, request):
        raise NotImplementedError

    def list(self, request):
        raise NotImplementedError

    def meta(self, request):
        return transformer.render(self.form)

    def show(self, request):
        raise NotImplementedError

    def create(self, request):
        raise NotImplementedError

    def update(self, request):
        raise NotImplementedError

    def destroy(self, request):
        raise NotImplementedError
