import re
from django.db.models import Q

"""
  This module offers a translator object that takes simple sproutcore queries and
  converts them into django Q objects which can be used to filter django objects.
  It returns a django Q object, so that one can add additional flags to it (like user crendetials)

  There're some good python libraries for this, like
  - booleano
  - pyparsing
  - CocoPy

  But these are a bit of an overload for an engine that has to parse all client queries
  that come into the server. Also, the sproutcore sql syntax is rather limited and simple 
  too which makes it not too difficult to implement a library for it.
  Finally, using these libraries would only result in a parsed token-tree that still has to be 
  evaluated into a django tree.
  Given that, I deemed it easier to write a simple parser & tokenizer based on a couple of regular expressions
  to achieve something close to a full recursive descent parser.
"""

c_and = "and"
c_or = "or"
c_not = "not"

class logic_expression(object):
  """
    A small helper entity that keeps track of a current expression
  """
  has_and = False
  has_or = False
  has_not = False
  def __init__(self, list):
    for l in list:
      l = l.lower()
      if l==c_and:
        self.has_and = True
      elif l==c_or:
        self.has_or = True
      elif l==c_not:
        self.has_not = True

class translator(object):
  
  #todo:
  # - Support for NOT (not and, not or, not in, not contains, etc)
  # - Support for parenthsis for grouping
  # - Support for contains to understand whether it is a string or a colleciton
  # - support for in / any collections

  """
  http://docs.sproutcore.com/symbols/SC.Query.html#constructor
  http://docs.djangoproject.com/en/dev/ref/models/querysets/#queryset-api
  Operators:
  =
  !=
  <
  <=
  >
  >=
  BEGINS_WITH (checks if a string starts with another one)
  ENDS_WITH (checks if a string ends with another one)
  CONTAINS (checks if a string contains another one, or if an object is in an array)
  MATCHES (checks if a string is matched by a regexp,
  you will have to use a parameter to insert the regexp)

  ANY (checks if the thing on its left is contained in the array
  on its right, you will have to use a parameter to insert the array)

  *TYPE_IS (unary operator expecting a string containing the name
  of a Model class on its right side, only records of this type will match)

  Boolean Operators:
  AND
  OR
  *NOT
  Parenthesis for grouping:
  *( and )
  """
  
  django_operators = {
    "BEGINS_WITH":"startswith", #or istartswith
    "ENDS_WITH": "endswith", #or iendswith
    "NOT BEGINS_WITH":"~startswith", #or istartswith
    "NOT ENDS_WITH": "~endswith", #or iendswith
    "CONTAINS": "contains", #or contains, if the right parm is a string, not a collection
    "ICONTAINS": "icontains", #or contains, if the right parm is a string, not a collection
    "NOT CONTAINS": "~contains",
    "MATCHES": "regex", #or iregex
    "ANY": "in",
    "NOT ANY": "~in",
    "=": "exact", #or iexact
    "!=": "~exact", #special.
    "<": "lt",
    ">": "gt",
    ">=": "gte",
    "<=": "lte",
    "in": "in",
    "NOT IN": "~in",
    "NOT": "not"
  }
  
  stack = []
  
  """this expression finds the expression blocks in the whole statement"""
  big_block_expression = None

  """this expression finds field, operator, and value in one expression-block """
  small_block_expression = None
  
  """
    The init function compiles the regular expressions that are used to identify the blocks 
  """
  def __init__(self):
    """
      This expression matches actually one block expression in our statement. 
      I.e. in the query "where name_field = 'Douglas Adams' and age>42" it would return
      two matches: "name_field = 'Douglas Adams'"  and  "age<42"
    """
    ex1 = """       # (name_field = 'Douglas Adams' and not)
    [a-zA-Z\_\.]+       # Name of the Column that is to be queried
                # name_field
    \s?           # Optional whitespace between the Column and the operator
    (?:%s)          # The list of operators (from django_operators) joined by a bitwise or (|)
                # =
    .*?           # Any whitespace and the value of the expression
                # 'Douglas Adams'
    (?:%s|$)+       # List of logical operations (and, or, not) as well as the end of the file
                # 'and'
    \s?           # Optional whitespace
    (?:%s|$)?       # Another logical operation to also match (and not, or not, not and, not or)
                # 'not'
    """ % (self.operatorstring(), self.logicstring(), self.logicstring())
    
    """
      This expression matches the different parts in one block expression.
      I.e. in the expression 'name_field = 'Douglas Adams' it would return
      three matches: "name_field", "=", and "Douglas Adams"
    """
    ex2 = """
    ([a-zA-Z\_\.]+)     # The Name of the Column, this is group match 1
                # 'name_field'
    \s?           # Optional whitespace
    (%s)          # The operator, this is group match 2
                # '='
    \s?           # Optional whitespace
                # The value of the expression
                # 'Douglas Adams'
    (\'.*?\'|         # String value
    \{.*?\}|        # A parameter value
    [0-9]+|         # A Number value (currently, int only)
    \(.*?\))        # A in or any value
    """ % (self.operatorstring(),)
    
    self.big_block_expression = re.compile(ex1, re.IGNORECASE|re.DOTALL|re.VERBOSE)
    self.small_block_expression = re.compile(ex2, re.IGNORECASE|re.DOTALL|re.VERBOSE)
  
  """
    A couple of helper functions that comb through our operator dictionaries 
  """
  def logiclist(self):
    return (c_and, c_or, c_not)
  
  def logicstring(self):
    return "|".join(self.logiclist())
  
  def operatorlist(self):
    return [re.escape(f) for f in self.django_operators.keys()]
  
  def operatorstring(self):
    return "|".join(self.operatorlist())
  
  def parse(self, query, parameters = {}):
    """
      This function receives a sproutcore query and optional parameters,
      parses them, and returns a django Q object that can be used
      to filter the database in question
    """

    #if the query is empty, return an empty obj
    if len(query.strip())=="":
      return None

    self.stack = []
    
    ##first step, break into AND, or OR blocks
    m = self.big_block_expression.findall(query)

    #if there were no blocks, return none
    if m==None or len(m)==0:return None
    
    #No loop through the blocks and try to identify the parts
    for exp in m:
      if exp.strip()=="":continue
      
      #parse the individual group
      m = self.small_block_expression.search(exp)
      if m:
        if len(m.groups())==3:
          self.stack.append(m.groups())
      combinatorList = re.findall("(?:%s)+$" % (self.logicstring()), exp.strip(), re.IGNORECASE)
      if combinatorList != None:
        self.stack.append(combinatorList)
    
    #The main Q object
    obj = None
    combinator = None #the current logical combination expression

    def convert_value(value):
      """
        Convert the value that comes in as string to
        the right python datatype.
        Currently supports conversion to 
        int, string, tuple
      """
      #TODO: Use the Django Type Information from the model to
      #convert these to the right datatype (i.e. date, etc)

      #If we have a non-string alredy, return it
      if type(value)!=type(""):return value

      value = value.replace("'", "")
      
      #this is a number value
      if re.match("^[0-9]+$", value):
        return int(value)
      #this is a collection. we could also match against \(.*?\) but that takes longer and the solution below should suffice
      elif value[0]=="(":
        return [convert_value(x.strip()) 
              for x in tuple(value[1:-1].split(','))] #recursive list comprehension ftw.
      #string
      else:
        return value

    def evaluate_not(n, obj):
      """
        return a django Q object, and invert it, based on the value of n
      """
      if n:
        return ~obj
      else:
        return obj

    for entry in self.stack:
      if type(entry)==type(()): #got a tuple

        #this shouldn't happen, but nevertheless check for it to prevent accidental breaking here.
        if len(entry)!=3:continue

        lfield = entry[0]
        operator = self.django_operators[entry[1]]
        rfield = entry[2]

        #if the lfield contains dots, these have to be converted to __ as that is the django field seperator
        lfield = lfield.replace(".", "__")
        
        #try to find a replacement for the rfield in our parameters
        if rfield.find("{")!=-1:
          rfield_ = rfield.replace("{", "").replace("}", "")
          if parameters.get(rfield_):
            rfield = parameters.get(rfield_)

        #we have to try to convert the object type to int
        rfield = convert_value(rfield)

        kwargs = {
          #we remove the ~ that was added to mark inverted values
	  #also, we need to covnert to ascii, as django does not support unicode key fields
          "%s__%s" % (lfield.encode('ascii') , operator.replace("~", "")):
          rfield
        }
        
        #create a q object
        if combinator:
          
          #if the obj operator contains a ~ we have to invert it. this is because django doesn't have a
          #equivalent to != or not contains. instead, the opposite expresion has to be used.
          if operator[0]=="~":
            if combinator.has_not: combinator.has_not=False
            else: combinator.has_not=True
          
          if combinator.has_and:
            obj = obj & evaluate_not(combinator.has_not, Q(**kwargs))
          elif combinator.has_or:
            obj = obj | evaluate_not(combinator.has_not, Q(**kwargs))
        else:
          obj = evaluate_not(not operator.find("~"), Q(**kwargs))
      
      if obj and type(entry)==type([]):
        combinator = logic_expression(entry)
    
    return obj


if __name__=="__main__":
  print "run the unit tests to test the code"
