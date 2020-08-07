# compose
DI for Python 3 embracing Typing


Just getting this up and running. Documentation coming soon. 


# usage
  ```python
  """ make a compose object"""
  di_context = Compose()

  """configure it""" 
  with di_context.registry():
      Bind[SimpleImpl].to_self()
      Bind[InterfaceA].to(ImplA).as_singleton()
      
  """Use it"""
  di_context.provide(InterfaceA)
  ```
