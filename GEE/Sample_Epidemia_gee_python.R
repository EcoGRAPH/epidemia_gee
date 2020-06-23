# Packages importing
install.packages("reticulate")
library(reticulate)
library(dplyr)
 
use_condaenv("gee-demo", conda = "auto",required = TRUE)  # Using conds environment.
ee = import("ee")          # Import the Earth Engine library.
ee$Initialize()            # Trigger the authentication.
E = import("Ethiopia")     # Import Epidemia package.


# Using above package to get environment data between required dates.
E$Et$gee_to_drive('2009-01-01','2009-03-31')   # Where start and end dates can be anydates with same format.