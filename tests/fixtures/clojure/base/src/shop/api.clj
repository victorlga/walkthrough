(ns shop.api
  (:require [shop.pricing :as pricing]))

(defn handler [event]
  (pricing/describe (:amount event)))
