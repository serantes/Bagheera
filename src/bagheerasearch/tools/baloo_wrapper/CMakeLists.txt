cmake_minimum_required(VERSION 3.16)
project(baloo_query_wrapper)

find_package(ECM REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH})

find_package(Qt6 REQUIRED COMPONENTS Core)
find_package(KF6 REQUIRED COMPONENTS Baloo FileMetaData)

add_library(baloo_wrapper SHARED baloo_wrapper.cpp)

target_link_libraries(baloo_wrapper
    Qt6::Core
    KF6::Baloo
    KF6::BalooEngine
    KF6::FileMetaData
    KF6::CoreAddons
)

# Important: C++17 is necessary for the u"|" literal
set_target_properties(baloo_wrapper PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
    # We ensure that symbols marked as default are visible
    C_VISIBILITY_PRESET default
    CXX_VISIBILITY_PRESET default
    VISIBILITY_INLINES_HIDDEN OFF
)
