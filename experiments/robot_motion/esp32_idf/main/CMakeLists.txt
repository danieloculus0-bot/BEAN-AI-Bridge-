idf_component_register(SRCS "main.c" INCLUDE_DIRS "." "../..")
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../motion_logic.c"
    "${CMAKE_CURRENT_LIST_DIR}/../../motion_selftest.c")
